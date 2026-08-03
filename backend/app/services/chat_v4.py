from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator
from typing import Any

from app.config import Settings
from app.services import chat as legacy_chat


_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:bearer|apikey|api[_ -]?key|secret|token)\s*[:=]\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
)


def safe_error(error: BaseException) -> str:
    value = str(error).strip() or type(error).__name__
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub("[redacted]", value)
    return value[:500]


def _provider_order(provider: str, messages: list[dict[str, Any]]) -> list[str]:
    if provider != "auto":
        return [provider]

    if legacy_chat._is_large_request(messages):
        return [
            "groq",
            "sambanova",
            "gemini",
            "openrouter",
            "mistral",
            "cerebras",
            "groq_fast",
        ]

    return [
        "groq_fast",
        "groq",
        "sambanova",
        "openrouter",
        "mistral",
        "cerebras",
    ]


def _streaming_order(provider: str, messages: list[dict[str, Any]]) -> list[str]:
    return [
        name
        for name in _provider_order(provider, messages)
        if name != "gemini"
    ]


def _answer_chunks(answer: str, size: int = 72) -> list[str]:
    if not answer:
        return []
    return [answer[index:index + size] for index in range(0, len(answer), size)]


def provider_diagnostics_snapshot(settings: Settings) -> dict[str, Any]:
    now = time.monotonic()
    configured = {
        "groq_fast": bool(settings.groq_api_key),
        "groq": bool(settings.groq_api_key),
        "sambanova": bool(settings.sambanova_api_key),
        "cerebras": bool(settings.cerebras_api_key),
        "gemini": bool(settings.google_gemini_api),
        "openrouter": bool(settings.openrouter_api),
        "mistral": bool(settings.mistral_ai_api),
    }
    models = {
        "groq_fast": settings.groq_fast_model,
        "groq": settings.groq_model,
        "sambanova": settings.sambanova_model,
        "cerebras": settings.cerebras_model,
        "gemini": settings.gemini_model,
        "openrouter": settings.openrouter_model,
        "mistral": settings.mistral_model,
    }

    result: dict[str, Any] = {}
    for name, is_configured in configured.items():
        cooldown_until = legacy_chat._PROVIDER_COOLDOWN_UNTIL.get(name, 0.0)
        result[name] = {
            "configured": is_configured,
            "model": models[name],
            "cooling_down": cooldown_until > now,
            "cooldown_remaining_seconds": max(0, round(cooldown_until - now)),
        }
    return result


async def route_chat_stream_v4(
    provider: str,
    messages: list[dict[str, Any]],
    settings: Settings,
    web_context: str = "",
    *,
    require_current: bool = False,
    as_of: str | None = None,
) -> AsyncIterator[dict[str, str]]:
    """Fast fallback with separate first-token and total provider deadlines."""

    if legacy_chat._is_large_request(messages):
        total_timeout = min(
            max(float(settings.total_chat_timeout_seconds), 40.0) + 20.0,
            90.0,
        )
        answer, provider_name = await asyncio.wait_for(
            legacy_chat.route_chat(
                provider,
                messages,
                settings,
                web_context,
                require_current=require_current,
                as_of=as_of,
            ),
            timeout=total_timeout,
        )
        yield {"type": "provider", "provider": provider_name}
        for chunk in _answer_chunks(answer):
            yield {"type": "token", "token": chunk}
            await asyncio.sleep(0)
        return

    errors: list[str] = []
    first_token_timeout = max(
        2.0,
        float(getattr(settings, "first_token_timeout_seconds", 6)),
    )

    for name in _streaming_order(provider, messages):
        if not legacy_chat._provider_is_available(name):
            errors.append(f"{name}: cooling down")
            yield {
                "type": "diagnostic",
                "provider": name,
                "status": "cooling_down",
            }
            continue

        emitted = False
        iterator = legacy_chat._stream_openai_compatible(
            name=name,
            messages=messages,
            settings=settings,
            web_context=web_context,
            require_current=require_current,
            as_of=as_of,
        )

        total_timeout = (
            float(settings.fast_provider_timeout_seconds)
            if name == "groq_fast"
            else float(settings.provider_timeout_seconds)
        )
        started = time.monotonic()

        try:
            yield {
                "type": "diagnostic",
                "provider": name,
                "status": "trying",
            }

            first_token = await asyncio.wait_for(
                anext(iterator),
                timeout=min(first_token_timeout, total_timeout),
            )
            emitted = True
            yield {"type": "provider", "provider": name}
            yield {"type": "token", "token": first_token}

            while True:
                remaining = total_timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise asyncio.TimeoutError(
                        f"{name} exceeded its total response timeout"
                    )
                try:
                    token = await asyncio.wait_for(
                        anext(iterator),
                        timeout=remaining,
                    )
                except StopAsyncIteration:
                    break
                yield {"type": "token", "token": token}

            legacy_chat._clear_provider_failure(name)
            yield {
                "type": "diagnostic",
                "provider": name,
                "status": "completed",
            }
            return
        except StopAsyncIteration:
            error = RuntimeError("Provider returned an empty stream")
            legacy_chat._mark_provider_failure(name, error, settings)
            errors.append(f"{name}: empty stream")
        except Exception as exc:
            legacy_chat._mark_provider_failure(name, exc, settings)
            clean = safe_error(exc)
            errors.append(f"{name}: {clean}")
            yield {
                "type": "diagnostic",
                "provider": name,
                "status": "failed",
                "error": clean,
            }
            if emitted:
                raise RuntimeError(
                    f"{name} streaming stopped after output began: {clean}"
                ) from exc
        finally:
            try:
                await iterator.aclose()
            except Exception:
                pass

    raise RuntimeError(
        "All streaming providers failed. " + " | ".join(errors[-6:])
    )
