from __future__ import annotations
import asyncio, hashlib, time
from collections.abc import AsyncIterator
from typing import Any
from app.config import Settings
from app.services import chat as legacy
from app.services.cache_v7 import RESPONSE_CACHE, norm
from app.services.chat_v4 import safe_error
from app.services.chat_v5 import _stream_provider_segment, build_resume_messages
from app.services.router_v7 import base_candidates, classify_route, configured_provider, last_user_query
from app.services.telemetry_v7 import available, attempt, success, failure, record
from app.services.quality_v9 import rank_for_task
from app.v13.context import compress_messages
from app.v13.incidents import recovery_plan
from app.v47.reliability_router import (
    adaptive_reliability_order,
    first_token_timeout_for_provider,
    observe_provider_failure,
    observe_provider_success,
    persist_failure_later,
    persist_success_later,
    provider_available as v47_provider_available,
    reliability_score as v47_reliability_score,
)

def _chunks(s,size=80): return [s[i:i+size] for i in range(0,len(s),size)]

def _cache_key(messages,tier):
    if len(messages)>2: return None
    q=last_user_query(messages).strip()
    if not q or len(q)>500: return None
    low=q.casefold()
    if any(x in low for x in ("my ","mere ","mera ","mujhe ","remember","yaad","today","latest","current","abhi")): return None
    return hashlib.sha256(f"{tier}|{norm(q)}".encode()).hexdigest()

def _provider_family(name: str | None) -> str:
    value = str(name or "").strip().casefold()
    if value.startswith("cache:"):
        value = value.split(":", 1)[1]
    if value in {"groq", "groq_fast"}:
        return "groq"
    return value


def _reaction_priority(
    names: list[str],
    tier: str,
) -> list[str]:
    ordered = list(dict.fromkeys(names))

    # The small Groq route exists specifically for low-latency
    # first-token responses.
    if tier == "fast" and "groq_fast" in ordered:
        ordered.remove("groq_fast")
        ordered.insert(0, "groq_fast")

    # Gemini currently uses a non-streaming adapter in this
    # router, therefore keep it as a fallback when streaming
    # alternatives exist.
    if "gemini" in ordered and len(ordered) > 1:
        ordered.remove("gemini")
        ordered.append("gemini")

    return ordered


def _select_chat_candidates(
    decision,
    provider: str,
    settings: Settings,
    *,
    max_attempts: int,
    excluded_family: str,
) -> tuple[list[str], bool]:
    """Select healthy candidates with V47 self-healing runtime ranking.

    V12/V13 quality ranking remains the anchor. V47 only reorders a small
    quality band using real latency/reliability observations and removes
    providers whose task-specific circuit is currently open.
    """
    configured = [
        name
        for name in base_candidates(decision, provider)
        if configured_provider(name, settings)
    ]
    base = [
        name
        for name in configured
        if legacy._provider_is_available(name)
    ]
    healthy = [
        name for name in base
        if available(name) and v47_provider_available(name, decision.task_type)
    ]

    def allowed(names: list[str]) -> list[str]:
        return [
            name
            for name in names
            if (
                not excluded_family
                or _provider_family(name) != excluded_family
            )
        ]

    def ranked(names: list[str]) -> list[str]:
        quality_ranked = _reaction_priority(
            rank_for_task(names, decision.task_type),
            decision.tier,
        )
        return adaptive_reliability_order(
            quality_ranked,
            decision.task_type,
            decision.tier,
            settings,
        )

    alternatives = allowed(healthy)
    candidates = ranked(alternatives)[:max_attempts]

    if not candidates:
        alternatives = allowed(base)
        # If all V47 circuits are open, preserve the existing shared-health
        # fallback behavior instead of declaring the system unavailable.
        candidates = ranked(alternatives)[:max_attempts]

    if not candidates:
        candidates = ranked(healthy or base)[:max_attempts]

    if candidates:
        return candidates, False

    if not bool(
        getattr(
            settings,
            "v18_chat_provider_recovery_enabled",
            True,
        )
    ):
        return [], False

    recovery_limit = max(
        1,
        min(
            max_attempts,
            int(
                getattr(
                    settings,
                    "v18_chat_recovery_max_attempts",
                    5,
                )
            ),
        ),
    )
    emergency = allowed(configured)
    emergency = ranked(emergency)[:recovery_limit]
    return emergency, bool(emergency)

async def route_chat_stream_v7(
    provider: str,
    messages: list[dict[str, Any]],
    settings: Settings,
    web_context: str = "",
    *,
    require_current: bool = False,
    as_of: str | None = None,
    cache_bypass: bool = False,
    exclude_provider: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    started = time.perf_counter()
    messages = compress_messages(
        messages,
        max_chars=int(getattr(settings, "max_context_chars", 45000)),
        preserve_last=12,
    )
    d = classify_route(messages, require_current=require_current)
    q = last_user_query(messages)
    max_attempts = max(1, min(7, int(getattr(settings, "max_provider_attempts", 7))))
    excluded_family = _provider_family(exclude_provider)
    candidates, recovery_mode = _select_chat_candidates(
        d,
        provider,
        settings,
        max_attempts=max_attempts,
        excluded_family=excluded_family,
    )
    if not candidates:
        raise RuntimeError("No configured AI provider is currently available.")

    ckey = None
    if (
        (not cache_bypass)
        and getattr(settings, "response_cache_enabled", True)
        and not require_current
        and not web_context.strip()
        and d.task_type in {"simple", "general"}
    ):
        ckey = _cache_key(messages, d.tier)
        if ckey:
            hit = RESPONSE_CACHE.get(ckey)
            if hit:
                answer, cached_provider = hit
                yield {
                    "type": "provider",
                    "provider": f"cache:{cached_provider}",
                    "attempt_count": 0,
                    "adaptive_routing": False,
                    "router_version": "v47-cache",
                }
                for chunk in _chunks(answer):
                    yield {"type": "token", "token": chunk}
                    await asyncio.sleep(0)
                record({
                    "task_type": d.task_type,
                    "tier": d.tier,
                    "language": d.language,
                    "provider": f"cache:{cached_provider}",
                    "attempts": 0,
                    "latency_ms": round((time.perf_counter() - started) * 1000),
                    "cache_hit": True,
                })
                return

    complete = ""
    errors: list[str] = []
    visible_first_token_ms: float | None = None
    attempts = 0
    final_provider = ""

    if recovery_mode:
        yield {
            "type": "diagnostic",
            "provider": "",
            "status": "v18_recovery:shared-cooldown-last-resort",
        }

    for name in candidates:
        attempts += 1
        attempt(name)
        pstarted = time.perf_counter()
        attempt_first_token_ms: float | None = None
        working = build_resume_messages(messages, complete)
        emitted = False
        provider_model = ""

        yield {
            "type": "diagnostic",
            "provider": name,
            "status": f"trying:{d.task_type}:{d.tier}:v47",
        }

        try:
            if name == "gemini":
                provider_model = str(getattr(settings, "gemini_model", "") or "")
                answer = await asyncio.wait_for(
                    legacy.chat_gemini(
                        working,
                        settings,
                        web_context,
                        require_current=require_current,
                        as_of=as_of,
                        temperature=0.0 if require_current else 0.2,
                    ),
                    timeout=float(getattr(settings, "large_provider_timeout_seconds", 45)),
                )
                if not answer.strip():
                    raise RuntimeError("Gemini returned an empty answer")

                final_provider = name
                emitted = True
                attempt_first_token_ms = round((time.perf_counter() - pstarted) * 1000, 1)
                if visible_first_token_ms is None:
                    visible_first_token_ms = round((time.perf_counter() - started) * 1000, 1)
                yield {
                    "type": "provider",
                    "provider": name,
                    "model": provider_model,
                    "first_token_ms": visible_first_token_ms,
                    "provider_first_token_ms": attempt_first_token_ms,
                    "attempt_count": attempts,
                    "adaptive_routing": True,
                    "router_version": "v47",
                    "reliability_score": v47_reliability_score(name, d.task_type),
                }
                for chunk in _chunks(answer):
                    complete += chunk
                    yield {"type": "token", "token": chunk}
                    await asyncio.sleep(0)
            else:
                try:
                    provider_model = str(legacy._stream_provider_config(name, settings)[2] or "")
                except Exception:
                    provider_model = ""

                max_cont = max(0, min(4, int(getattr(settings, "max_continuations", 2))))
                for idx in range(max_cont + 1):
                    segment = ""
                    finish = ""
                    it = _stream_provider_segment(
                        name=name,
                        messages=working,
                        settings=settings,
                        web_context=web_context,
                        require_current=require_current,
                        as_of=as_of,
                        large_request=d.tier == "strong",
                    )
                    try:
                        first_token_timeout = first_token_timeout_for_provider(
                            name,
                            d.task_type,
                            tier=d.tier,
                            settings=settings,
                            recovery_mode=recovery_mode,
                        )
                        ev = await asyncio.wait_for(
                            anext(it),
                            timeout=first_token_timeout,
                        )
                        pending = [ev]
                        while pending:
                            e = pending.pop(0)
                            if e.get("type") == "token":
                                token = e.get("token", "")
                                if token:
                                    if not emitted:
                                        emitted = True
                                        final_provider = name
                                        attempt_first_token_ms = round(
                                            (time.perf_counter() - pstarted) * 1000,
                                            1,
                                        )
                                        if visible_first_token_ms is None:
                                            visible_first_token_ms = round(
                                                (time.perf_counter() - started) * 1000,
                                                1,
                                            )
                                        yield {
                                            "type": "provider",
                                            "provider": name,
                                            "model": provider_model,
                                            "first_token_ms": visible_first_token_ms,
                                            "provider_first_token_ms": attempt_first_token_ms,
                                            "attempt_count": attempts,
                                            "adaptive_routing": True,
                                            "router_version": "v47",
                                            "reliability_score": v47_reliability_score(name, d.task_type),
                                        }
                                    segment += token
                                    complete += token
                                    yield {"type": "token", "token": token}
                            elif e.get("type") == "finish":
                                finish = e.get("reason", "")

                        async for e in it:
                            if e.get("type") == "token":
                                token = e.get("token", "")
                                if token:
                                    if not emitted:
                                        emitted = True
                                        final_provider = name
                                        attempt_first_token_ms = round(
                                            (time.perf_counter() - pstarted) * 1000,
                                            1,
                                        )
                                        if visible_first_token_ms is None:
                                            visible_first_token_ms = round(
                                                (time.perf_counter() - started) * 1000,
                                                1,
                                            )
                                        yield {
                                            "type": "provider",
                                            "provider": name,
                                            "model": provider_model,
                                            "first_token_ms": visible_first_token_ms,
                                            "provider_first_token_ms": attempt_first_token_ms,
                                            "attempt_count": attempts,
                                            "adaptive_routing": True,
                                            "router_version": "v47",
                                            "reliability_score": v47_reliability_score(name, d.task_type),
                                        }
                                    segment += token
                                    complete += token
                                    yield {"type": "token", "token": token}
                            elif e.get("type") == "finish":
                                finish = e.get("reason", "")
                    finally:
                        try:
                            await it.aclose()
                        except Exception:
                            pass

                    if not segment:
                        raise RuntimeError("Provider returned an empty stream")
                    if legacy._is_length_finish(finish) and idx < max_cont:
                        working.extend([
                            {"role": "assistant", "content": segment},
                            {"role": "user", "content": legacy._continuation_instruction()},
                        ])
                        yield {
                            "type": "diagnostic",
                            "provider": name,
                            "status": "automatic_continuation:v47",
                        }
                        continue
                    break

            total_provider_ms = round((time.perf_counter() - pstarted) * 1000, 1)
            learned = observe_provider_success(
                name,
                d.task_type,
                first_token_ms=attempt_first_token_ms or total_provider_ms,
                total_latency_ms=total_provider_ms,
            )
            persist_success_later(
                settings,
                name,
                d.task_type,
                first_token_ms=attempt_first_token_ms or total_provider_ms,
                total_latency_ms=total_provider_ms,
            )
            success(name, round(total_provider_ms))
            legacy._clear_provider_failure(name)

            if ckey and complete.strip():
                RESPONSE_CACHE.set(
                    ckey,
                    (complete.strip(), name),
                    int(getattr(settings, "response_cache_ttl_seconds", 900)),
                )

            record({
                "task_type": d.task_type,
                "difficulty": d.difficulty,
                "tier": d.tier,
                "language": d.language,
                "message_chars": len(q),
                "estimated_input_tokens": max(
                    1,
                    sum(len(str(m.get("content") or "")) for m in messages) // 4,
                ),
                "estimated_output_tokens": max(1, len(complete) // 4),
                "provider": final_provider or name,
                "attempts": attempts,
                "first_token_ms": visible_first_token_ms,
                "provider_first_token_ms": attempt_first_token_ms,
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "provider_latency_ms": total_provider_ms,
                "v47_success_rate": round(
                    learned.successes / max(1, learned.successes + learned.failures),
                    4,
                ),
                "cache_hit": False,
            })
            yield {
                "type": "diagnostic",
                "provider": name,
                "status": "completed:v47",
                "provider_latency_ms": total_provider_ms,
                "reliability_score": v47_reliability_score(name, d.task_type),
            }
            return

        except Exception as exc:
            failure(name, exc)
            legacy._mark_provider_failure(name, exc, settings)
            observe_provider_failure(name, d.task_type, exc, settings)
            persist_failure_later(settings, name, d.task_type, exc)

            clean = safe_error(exc)
            errors.append(f"{name}: {clean}")
            yield {
                "type": "diagnostic",
                "provider": name,
                "status": "failed:v47",
                "error": clean,
                "reliability_score": v47_reliability_score(name, d.task_type),
            }
            remaining = candidates[attempts:]
            recovery = recovery_plan(name, clean, remaining)
            yield {
                "type": "diagnostic",
                "provider": name,
                "status": f"v14_recovery:{recovery.incident_type}",
                "error": clean,
            }
            # Never turn cross-provider fallback into a moderation bypass.
            if recovery.incident_type == "moderation":
                complete = ""
                raise RuntimeError(
                    "Provider blocked this request under its moderation policy."
                )
            if emitted:
                yield {
                    "type": "diagnostic",
                    "provider": name,
                    "status": "resuming_same_tier:v47",
                }

    if complete.strip():
        return
    record({
        "task_type": d.task_type,
        "tier": d.tier,
        "language": d.language,
        "provider": final_provider,
        "attempts": attempts,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "error": " | ".join(errors[-3:]),
    })
    raise RuntimeError(
        "All selected same-tier providers failed. " + " | ".join(errors[-3:])
    )
