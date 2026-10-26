from __future__ import annotations

import asyncio
import time

from fastapi import Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

import app.main as legacy
import app.main_v4 as v4
from app.auth import AuthUser, get_current_user
from app.services.chat_v5 import route_chat_stream_v5
from app.services.error_monitoring import record_error_event
from app.services.memory_v5 import remember_with_conflict_resolution
from app.services.quota_v5 import check_chat_quota
from app.services.rate_limit import QuotaExceeded
from app.v13.critic import critic_review
from app.v53.intelligence_core import build_intelligence_contract
from app.v54.knowledge_brain import assess_and_rank_sources
from app.v57.coding_brain import build_coding_policy
from app.v58.fresh_facts import fresh_fact_answer_policy
from app.v59.fresh_fact_resolver import fresh_fact_evidence_context
from app.v67.reliability import observe_truth_guard


app = v4.app
settings = v4.settings

# Keep v4 diagnostics middleware and parallel-context helpers, but replace
# only its stream route.
v4._remove_route("/api/chat/stream", "POST")


@app.post("/api/chat/stream")
async def chat_stream_v5(
    chat_request: legacy.ChatRequest,
    http_request: Request,
    current_user: AuthUser = Depends(get_current_user),
) -> StreamingResponse:
    request_id = v4._request_id(http_request)
    minute_limit = int(getattr(settings, "rate_limit_per_minute", 15))
    daily_limit = int(getattr(settings, "daily_message_limit", 250))

    try:
        quota = await check_chat_quota(
            current_user.id,
            settings,
            minute_limit=minute_limit,
            daily_limit=daily_limit,
        )
    except QuotaExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail=f"{exc} Retry after {exc.retry_after_seconds} seconds.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    raw_messages = [item.model_dump() for item in chat_request.messages]
    query = next(
        (
            item["content"]
            for item in reversed(raw_messages)
            if item["role"] == "user"
        ),
        "",
    )
    current_date = legacy._current_date()

    identity_answer = legacy.fixed_identity_reply(query)
    if identity_answer:
        return legacy._direct_stream(
            identity_answer,
            provider="vasuki-identity",
        )

    explicit_memory, memory_followup = (
        legacy.extract_explicit_memory_command(query)
        if chat_request.use_memory
        else (None, "")
    )
    memory_action_context = ""
    if explicit_memory:
        memory_saved = False
        try:
            await remember_with_conflict_resolution(
                current_user.id,
                explicit_memory,
                settings,
                category=legacy.explicit_memory_category(explicit_memory),
                user_jwt=current_user.access_token,
            )
            memory_saved = True
            answer = f"I will remember: {explicit_memory}"
        except ValueError as exc:
            answer = str(exc)
        except Exception as exc:
            v4._log(
                "memory_save_failed",
                request_id=request_id,
                error=v4.safe_error(exc),
            )
            asyncio.create_task(
                record_error_event(
                    settings,
                    request_id=request_id,
                    event_type="memory_save_failed",
                    error=exc,
                )
            )
            answer = (
                "The memory could not be saved right now. "
                f"Request ID: {request_id}"
            )

        if not memory_followup:
            return legacy._direct_stream(
                answer,
                provider="vasuki-personal-memory",
            )

        if memory_saved:
            memory_action_context = (
                "SYSTEM ACTION RESULT:\n"
                "The user's explicit memory was saved successfully.\n"
                f"MEMORY: {explicit_memory}\n"
                "Continue with the remaining user request. "
                "Do not stop at a memory acknowledgement."
            )
        else:
            memory_action_context = (
                "SYSTEM ACTION RESULT:\n"
                "The user asked to save an explicit memory, but "
                "persistence failed. Use it only for this turn.\n"
                f"ATTEMPTED MEMORY: {explicit_memory}\n"
                "Answer the remaining request and briefly mention "
                "that persistence did not succeed."
            )

        query = memory_followup
        raw_messages = legacy._replace_last_user_content(
            raw_messages,
            memory_followup,
        )

    (
        strong_hits,
        shared_sources,
        shared_pack,
        private_pack,
        document_sources,
        require_current,
        web_sources,
        live_pack,
    ) = await v4._parallel_context(
        user=current_user,
        query=query,
        chat_request=chat_request,
    )

    # V59 defense-in-depth: classification remains current-sensitive even if a
    # lower context layer returned a degraded result.
    require_current = bool(
        require_current
        or legacy.needs_live_web(query)
        or bool(getattr(chat_request, "research_mode", False))
    )

    if (
        strong_hits
        and legacy.is_direct_fact_question(query)
        and not chat_request.use_web
        and not chat_request.use_documents
    ):
        return legacy._direct_stream(
            strong_hits[0].answer,
            provider="vasuki-global-memory",
            sources=shared_sources,
        )

    if require_current and not web_sources and not strong_hits:
        observe_truth_guard("live-verification-unavailable")
        return legacy._direct_stream(
            (
                "The live verification service is temporarily unavailable. "
                "Please retry in a few seconds so outdated information is not guessed."
            ),
            provider="truth-guard",
            sources=document_sources,
        )

    missing = legacy._missing_state_evidence(query, web_sources)
    if missing:
        return legacy._direct_stream(
            (
                "The complete list could not be safely verified. Missing evidence: "
                + ", ".join(missing)
            ),
            provider="truth-guard",
            sources=web_sources,
        )

    v50_assessment, v50_policy, v50_block = legacy._v50_current_guard(
        query,
        web_sources,
        require_current=require_current,
    )

    if v50_block:
        observe_truth_guard("v50-insufficient-current-evidence")
        return legacy._direct_stream(
            legacy.truth_guard_message(v50_assessment),
            provider="v50-truth-guard",
            sources=web_sources,
        )

    live_pack = legacy._join_context(
        v50_policy,
        live_pack,
    )

    evidence = assess_and_rank_sources(
        query,
        web_sources,
        current_required=require_current,
        limit=10,
    )
    web_sources = list(evidence.sources)

    fresh_fact_resolution = fresh_fact_evidence_context(
        query,
        web_sources,
        as_of=current_date,
    )

    project_active = bool(
        str(
            getattr(
                chat_request,
                "project_id",
                "",
            )
            or ""
        ).strip()
    )

    intelligence = build_intelligence_contract(
        raw_messages,
        require_current=require_current,
        project_active=project_active,
        evidence_confidence=(
            evidence.confidence
            if web_sources
            else None
        ),
    )

    coding_policy = build_coding_policy(
        raw_messages,
        project_active=project_active,
    )

    research_instruction = ""
    if bool(getattr(chat_request, "research_mode", False)):
        research_instruction = (
            "DEEP RESEARCH V2: Cross-check important claims across the supplied sources. "
            "Prefer authoritative and recent evidence, distinguish confirmed facts from inference, "
            "mention material disagreement, and never invent citations or unsupported claims."
        )
    web_context = legacy._join_context(
        fresh_fact_answer_policy(
            query,
            as_of=current_date,
        ),
        fresh_fact_resolution,
        intelligence.context,
        evidence.context if web_sources else "",
        coding_policy,
        research_instruction,
        shared_pack,
        private_pack,
        live_pack,
        memory_action_context,
    )
    available_message_chars = max(
        8000,
        settings.max_context_chars
        - len(web_context)
        - settings.context_reserve_chars,
    )
    messages, context_stats = legacy.compact_messages(
        raw_messages,
        max_chars=available_message_chars,
        max_single_message_chars=settings.max_single_message_chars,
    )
    all_sources = shared_sources + document_sources + web_sources

    async def generate():
        provider_name = ""
        provider_model = ""
        first_token_ms = None
        provider_first_token_ms = None
        attempt_count = 0
        adaptive_routing = False
        router_version = ""
        reliability_score = None
        complete_answer = ""
        started = time.perf_counter()

        try:
            yield legacy._sse(
                "ready",
                {
                    "request_id": request_id,
                    "context_trimmed": context_stats.trimmed,
                    "original_context_chars": context_stats.original_chars,
                    "used_context_chars": context_stats.used_chars,
                    "minute_limit": quota.minute_limit,
                    "minute_remaining": quota.minute_remaining,
                    "daily_limit": quota.daily_limit,
                    "daily_remaining": quota.daily_remaining,
                    "intelligence_mode": intelligence.mode,
                    "intelligence_confidence": intelligence.confidence,
                    "verification_required": intelligence.verification_required,
                    "activity": intelligence.activity,
                    "evidence_confidence": evidence.confidence,
                    "evidence_disagreement": evidence.disagreement,
                },
            )

            async for event in route_chat_stream_v5(
                chat_request.provider,
                messages,
                settings,
                web_context,
                require_current=require_current,
                as_of=current_date,
                cache_bypass=bool(getattr(chat_request, "cache_bypass", False)),
                exclude_provider=getattr(chat_request, "exclude_provider", None),
            ):
                if await http_request.is_disconnected():
                    return

                event_type = event.get("type")
                if event_type == "provider":
                    provider_name = event.get("provider", "")
                    provider_model = event.get("model", "")
                    first_token_ms = event.get("first_token_ms")
                    provider_first_token_ms = event.get("provider_first_token_ms")
                    attempt_count = int(event.get("attempt_count") or 0)
                    adaptive_routing = bool(event.get("adaptive_routing"))
                    router_version = str(event.get("router_version") or "")
                    reliability_score = event.get("reliability_score")
                    yield legacy._sse(
                        "provider",
                        {
                            "provider": provider_name,
                            "provider_model": provider_model,
                            "first_token_ms": first_token_ms,
                            "provider_first_token_ms": provider_first_token_ms,
                            "attempt_count": attempt_count,
                            "adaptive_routing": adaptive_routing,
                            "router_version": router_version,
                            "reliability_score": reliability_score,
                        },
                    )
                elif event_type == "token":
                    token = str(
                        event.get("token", "")
                        or ""
                    )
                    complete_answer += token
                    yield legacy._sse(
                        "token",
                        {"token": token},
                    )
                elif event_type == "diagnostic":
                    v4._log(
                        "provider_attempt",
                        request_id=request_id,
                        provider=event.get("provider", ""),
                        status=event.get("status", ""),
                        error=event.get("error", ""),
                    )
                    yield legacy._sse(
                        "diagnostic",
                        {
                            "provider": event.get("provider", ""),
                            "status": event.get("status", ""),
                        },
                    )

            quality = critic_review(
                query,
                complete_answer,
                sources=all_sources,
                current_required=require_current,
            )

            duration_ms = round(
                (time.perf_counter() - started) * 1000
            )
            v4._log(
                "chat_completed",
                request_id=request_id,
                provider=provider_name or "auto",
                duration_ms=duration_ms,
            )
            yield legacy._sse(
                "meta",
                {
                    "request_id": request_id,
                    "provider": provider_name or "auto",
                    "provider_model": provider_model,
                    "first_token_ms": first_token_ms,
                    "provider_first_token_ms": provider_first_token_ms,
                    "duration_ms": duration_ms,
                    "attempt_count": attempt_count,
                    "adaptive_routing": adaptive_routing,
                    "router_version": router_version,
                    "reliability_score": reliability_score,
                    "sources": all_sources,
                    "context_trimmed": context_stats.trimmed,
                    "original_context_chars": context_stats.original_chars,
                    "used_context_chars": context_stats.used_chars,
                    "minute_limit": quota.minute_limit,
                    "minute_remaining": quota.minute_remaining,
                    "daily_limit": quota.daily_limit,
                    "daily_remaining": quota.daily_remaining,
                    "intelligence_mode": intelligence.mode,
                    "intelligence_confidence": intelligence.confidence,
                    "verification_required": intelligence.verification_required,
                    "evidence_confidence": evidence.confidence,
                    "evidence_disagreement": evidence.disagreement,
                    "quality_checked": True,
                    "quality_score": quality.score,
                    "quality_issues": list(quality.issues[:4]),
                    "done": True,
                },
            )
        except asyncio.CancelledError:
            return
        except Exception as exc:
            v4._log(
                "chat_stream_failed",
                request_id=request_id,
                provider=provider_name or "unknown",
                error_type=type(exc).__name__,
                error=v4.safe_error(exc),
            )
            asyncio.create_task(
                record_error_event(
                    settings,
                    request_id=request_id,
                    event_type="chat_stream_failed",
                    error=exc,
                    provider=provider_name or "unknown",
                )
            )
            yield legacy._sse(
                "error",
                {
                    "detail": (
                        "The AI provider failed to return a response. "
                        f"Request ID: {request_id}. Please try again."
                    ),
                    "request_id": request_id,
                },
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "X-Request-ID": request_id,
        },
    )
