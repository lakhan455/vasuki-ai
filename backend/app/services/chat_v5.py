from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import Settings
from app.services import chat as legacy_chat
from app.services.chat_v4 import safe_error


def _provider_order(
    provider: str,
    messages: list[dict[str, Any]],
) -> list[str]:
    if provider != "auto":
        return [provider]

    if legacy_chat._is_large_request(messages):
        return [
            "groq",
            "sambanova",
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
) -> AsyncIterator[dict[str, str]]:
    """True token streaming with continuation and fallback recovery."""

    large_request = legacy_chat._is_large_request(messages)
    first_token_timeout = max(
        2.0,
        float(getattr(settings, "first_token_timeout_seconds", 6)),
    )
    max_continuations = max(
        0,
        min(4, int(getattr(settings, "max_continuations", 2))),
    )
    complete_text = ""
    errors: list[str] = []

    for name in _provider_order(provider, messages):
        if not legacy_chat._provider_is_available(name):
            errors.append(f"{name}: cooling down")
            yield {
                "type": "diagnostic",
                "provider": name,
                "status": "cooling_down",
            }
            continue

        working_messages = build_resume_messages(messages, complete_text)
        provider_emitted = False

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
                                    yield {
                                        "type": "provider",
                                        "provider": name,
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
                                    yield {
                                        "type": "provider",
                                        "provider": name,
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
                        "\n\n[Answer provider limit tak pahunch gaya. "
                        "Agla part maangne ke liye “continue” bhejein.]"
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
