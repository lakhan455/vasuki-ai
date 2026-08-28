from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import Settings
from app.services import chat as legacy_chat
from app.services.chat_v4 import safe_error
from app.services.router_v7 import base_candidates, classify_route, configured_provider
from app.v46.adaptive_speed import (
    adaptive_provider_order,
    first_token_timeout_seconds,
    record_provider_failure,
    record_provider_success,
)
# VASUKI_V45_PROVIDER_DIAGNOSTICS_IMPORTS


def _provider_order(
    provider: str,
    messages: list[dict[str, Any]],
    settings: Settings | None = None,
    *,
    exclude_provider: str | None = None,
) -> list[str]:
    if provider != "auto":
        return [provider]

    decision = classify_route(messages)
    if decision.task_type == "code":
        order = [
            "opencode_zen",
            "zai_glm",
            "groq",
            "openrouter",
            "mistral",
            "cerebras",
            "sambanova",
            "groq_fast",
        ]
    else:
        order = base_candidates(decision, "auto")

    stream_capable = {
        "groq_fast",
        "groq",
        "sambanova",
        "cerebras",
        "opencode_zen",
        "zai_glm",
        "openrouter",
        "mistral",
    }
    order = [name for name in order if name in stream_capable]

    if settings is not None:
        order = [name for name in order if configured_provider(name, settings)]

    if exclude_provider:
        order = [name for name in order if name != exclude_provider]

    if settings is not None:
        order = adaptive_provider_order(
            order,
            decision.task_type,
            enabled=bool(getattr(settings, "v46_adaptive_speed_enabled", True)),
            min_samples=int(getattr(settings, "v46_adaptive_min_samples", 2)),
        )

    return order


def build_resume_messages(
    messages: list[dict[str, Any]],
    partial_answer: str,
) -> list[dict[str, Any]]:
    if not partial_answer.strip():
        return [dict(item) for item in messages]

    return [
        *[dict(item) for item in messages],
        {"role": "assistant", "content": partial_answer},
        {
            "role": "user",
            "content": (
                legacy_chat._continuation_instruction()
                + " Continue from the visible partial answer even if the "
                "previous provider failed. Do not repeat text."
            ),
        },
    ]


async def _stream_provider_segment(
    *,
    name: str,
    messages: list[dict[str, Any]],
    settings: Settings,
    web_context: str,
    require_current: bool,
    as_of: str | None,
    large_request: bool,
) -> AsyncIterator[dict[str, str]]:
    url, api_key, model, token_field, extra_headers = (
        legacy_chat._stream_provider_config(name, settings)
    )
    if not api_key:
        raise RuntimeError(f"{name} API key is not configured")

    output_limit = (
        min(settings.max_fast_output_tokens, settings.max_output_tokens)
        if name == "groq_fast"
        else settings.max_output_tokens
    )
    timeout_seconds = (
        float(getattr(settings, "large_provider_timeout_seconds", 45))
        if large_request and name != "groq_fast"
        else (
            float(settings.fast_provider_timeout_seconds)
            if name == "groq_fast"
            else float(settings.provider_timeout_seconds)
        )
    )

    payload = {
        "model": model,
        "messages": legacy_chat._openai_messages(
            messages,
            web_context,
            require_current=require_current,
            as_of=as_of,
        ),
        "temperature": 0.0 if require_current else 0.2,
        token_field: output_limit,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **extra_headers,
    }

    finish_reason = ""

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(
            timeout_seconds,
            connect=min(10.0, timeout_seconds),
            read=timeout_seconds,
            write=min(15.0, timeout_seconds),
            pool=min(10.0, timeout_seconds),
        )
    ) as client:
        async with client.stream(
            "POST",
            url,
            headers=headers,
            json=payload,
        ) as response:
            if response.is_error:
                raw = (
                    await response.aread()
                ).decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"{response.status_code} from {model}: {raw[:900]}"
                )

            async for line in response.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data:"):
                    continue

                data_text = line[5:].strip()
                if data_text == "[DONE]":
                    break

                try:
                    packet = json.loads(data_text)
                except json.JSONDecodeError:
                    continue

                choices = packet.get("choices") or []
                if not choices:
                    continue

                choice = choices[0] or {}
                reason = choice.get("finish_reason")
                if reason is not None:
                    finish_reason = str(reason)

                delta = choice.get("delta") or {}
                token = delta.get("content")
                if token:
                    yield {"type": "token", "token": str(token)}

    yield {"type": "finish", "reason": finish_reason}


async def route_chat_stream_v5(
    provider: str,
    messages: list[dict[str, Any]],
    settings: Settings,
    web_context: str = "",
    *,
    require_current: bool = False,
    as_of: str | None = None,
    cache_bypass: bool = False,
    exclude_provider: str | None = None,
) -> AsyncIterator[dict[str, str]]:
    """True token streaming with continuation and fallback recovery."""

    large_request = legacy_chat._is_large_request(messages)
    decision = classify_route(messages, require_current=require_current)
    first_token_timeout = first_token_timeout_seconds(
        decision.task_type,
        large_request=large_request,
        settings=settings,
    )
    max_continuations = max(
        0,
        min(4, int(getattr(settings, "max_continuations", 2))),
    )
    complete_text = ""
    errors: list[str] = []
    attempt_count = 0

    for name in _provider_order(
        provider,
        messages,
        settings,
        exclude_provider=exclude_provider,
    ):
        if not legacy_chat._provider_is_available(name):
            errors.append(f"{name}: cooling down")
            yield {
                "type": "diagnostic",
                "provider": name,
                "status": "cooling_down",
            }
            continue

        attempt_count += 1
        working_messages = build_resume_messages(messages, complete_text)
        provider_emitted = False
        attempt_started = time.perf_counter()
        first_token_ms = 0.0
        provider_model = ""

        try:
            for continuation_index in range(max_continuations + 1):
                segment_text = ""
                finish_reason = ""
                iterator = _stream_provider_segment(
                    name=name,
                    messages=working_messages,
                    settings=settings,
                    web_context=web_context,
                    require_current=require_current,
                    as_of=as_of,
                    large_request=large_request,
                )

                yield {
                    "type": "diagnostic",
                    "provider": name,
                    "status": (
                        "continuing"
                        if continuation_index > 0 or complete_text
                        else "trying"
                    ),
                }

                try:
                    first_event = await asyncio.wait_for(
                        anext(iterator),
                        timeout=first_token_timeout,
                    )

                    events = [first_event]
                    while events:
                        event = events.pop(0)
                        if event.get("type") == "token":
                            token = event.get("token", "")
                            if token:
                                if not provider_emitted:
                                    provider_emitted = True
                                    first_token_ms = round(
                                        (time.perf_counter() - attempt_started) * 1000,
                                        1,
                                    )
                                    try:
                                        provider_model = legacy_chat._stream_provider_config(
                                            name,
                                            settings,
                                        )[2]
                                    except Exception:
                                        provider_model = ""
                                    record_provider_success(
                                        name,
                                        first_token_ms,
                                        decision.task_type,
                                    )
                                    yield {
                                        "type": "provider",
                                        "provider": name,
                                        "model": provider_model,
                                        "first_token_ms": first_token_ms,
                                        "attempt_count": attempt_count,
                                        "adaptive_routing": True,
                                    }
                                segment_text += token
                                complete_text += token
                                yield {"type": "token", "token": token}
                        elif event.get("type") == "finish":
                            finish_reason = event.get("reason", "")

                    async for event in iterator:
                        if event.get("type") == "token":
                            token = event.get("token", "")
                            if token:
                                if not provider_emitted:
                                    provider_emitted = True
                                    first_token_ms = round(
                                        (time.perf_counter() - attempt_started) * 1000,
                                        1,
                                    )
                                    try:
                                        provider_model = legacy_chat._stream_provider_config(
                                            name,
                                            settings,
                                        )[2]
                                    except Exception:
                                        provider_model = ""
                                    record_provider_success(
                                        name,
                                        first_token_ms,
                                        decision.task_type,
                                    )
                                    yield {
                                        "type": "provider",
                                        "provider": name,
                                        "model": provider_model,
                                        "first_token_ms": first_token_ms,
                                        "attempt_count": attempt_count,
                                        "adaptive_routing": True,
                                    }
                                segment_text += token
                                complete_text += token
                                yield {"type": "token", "token": token}
                        elif event.get("type") == "finish":
                            finish_reason = event.get("reason", "")
                finally:
                    try:
                        await iterator.aclose()
                    except Exception:
                        pass

                if not segment_text:
                    raise RuntimeError("Provider returned an empty stream")

                if (
                    legacy_chat._is_length_finish(finish_reason)
                    and continuation_index < max_continuations
                ):
                    working_messages.extend(
                        [
                            {
                                "role": "assistant",
                                "content": segment_text,
                            },
                            {
                                "role": "user",
                                "content": legacy_chat._continuation_instruction(),
                            },
                        ]
                    )
                    yield {
                        "type": "diagnostic",
                        "provider": name,
                        "status": "automatic_continuation",
                    }
                    continue

                if legacy_chat._is_length_finish(finish_reason):
                    notice = (
                        "\n\n[The answer reached the provider output limit. "
                        "Send “continue” to request the next part.]"
                    )
                    complete_text += notice
                    yield {"type": "token", "token": notice}

                legacy_chat._clear_provider_failure(name)
                yield {
                    "type": "diagnostic",
                    "provider": name,
                    "status": "completed",
                }
                return

        except Exception as exc:
            legacy_chat._mark_provider_failure(name, exc, settings)
            record_provider_failure(name, decision.task_type)
            clean = safe_error(exc)
            errors.append(f"{name}: {clean}")
            yield {
                "type": "diagnostic",
                "provider": name,
                "status": "failed",
                "error": clean,
            }

            if provider_emitted:
                yield {
                    "type": "diagnostic",
                    "provider": name,
                    "status": "resuming_with_fallback",
                }
                continue

    if complete_text.strip():
        return

    raise RuntimeError(
        "All streaming providers failed. " + " | ".join(errors[-6:])
    )
