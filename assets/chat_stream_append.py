
# ---------------------------------------------------------------------------
# True token streaming for OpenAI-compatible providers
# ---------------------------------------------------------------------------

import json as _stream_json
from collections.abc import AsyncIterator as _AsyncIterator


def _stream_provider_config(
    name: str,
    settings: Settings,
) -> tuple[str, str, str, str, dict[str, str]]:
    if name == "groq_fast":
        return (
            "https://api.groq.com/openai/v1/chat/completions",
            settings.groq_api_key or "",
            settings.groq_fast_model,
            "max_completion_tokens",
            {},
        )
    if name == "groq":
        return (
            "https://api.groq.com/openai/v1/chat/completions",
            settings.groq_api_key or "",
            settings.groq_model,
            "max_completion_tokens",
            {},
        )
    if name == "sambanova":
        return (
            f"{settings.sambanova_base_url.rstrip('/')}/chat/completions",
            settings.sambanova_api_key or "",
            settings.sambanova_model,
            "max_tokens",
            {},
        )
    if name == "cerebras":
        return (
            f"{settings.cerebras_base_url.rstrip('/')}/chat/completions",
            settings.cerebras_api_key or "",
            settings.cerebras_model,
            "max_completion_tokens",
            {},
        )
    if name == "openrouter":
        return (
            "https://openrouter.ai/api/v1/chat/completions",
            settings.openrouter_api or "",
            settings.openrouter_model,
            "max_tokens",
            {"X-Title": settings.app_name},
        )
    if name == "mistral":
        return (
            "https://api.mistral.ai/v1/chat/completions",
            settings.mistral_ai_api or "",
            settings.mistral_model,
            "max_tokens",
            {},
        )
    raise RuntimeError(f"{name} does not support this streaming route")


async def _stream_openai_compatible(
    *,
    name: str,
    messages: list[dict],
    settings: Settings,
    web_context: str,
    require_current: bool,
    as_of: str | None,
) -> _AsyncIterator[str]:
    url, api_key, model, token_field, extra_headers = _stream_provider_config(
        name,
        settings,
    )
    if not api_key:
        raise RuntimeError(f"{name} API key is not configured")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **extra_headers,
    }
    output_limit = (
        min(settings.max_fast_output_tokens, settings.max_output_tokens)
        if name == "groq_fast"
        else settings.max_output_tokens
    )
    payload = {
        "model": model,
        "messages": _openai_messages(
            messages,
            web_context,
            require_current=require_current,
            as_of=as_of,
        ),
        "temperature": 0.0 if require_current else 0.2,
        token_field: output_limit,
        "stream": True,
    }

    timeout_seconds = (
        float(settings.fast_provider_timeout_seconds)
        if name == "groq_fast"
        else float(settings.provider_timeout_seconds)
    )

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds, read=timeout_seconds)
    ) as client:
        async with client.stream(
            "POST",
            url,
            headers=headers,
            json=payload,
        ) as response:
            if response.is_error:
                raw = (await response.aread()).decode("utf-8", errors="replace")
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
                    payload = _stream_json.loads(data_text)
                except _stream_json.JSONDecodeError:
                    continue

                choices = payload.get("choices") or []
                if not choices:
                    continue

                delta = choices[0].get("delta") or {}
                token = delta.get("content")
                if token:
                    yield str(token)


async def route_chat_stream(
    provider: str,
    messages: list[dict],
    settings: Settings,
    web_context: str = "",
    *,
    require_current: bool = False,
    as_of: str | None = None,
) -> _AsyncIterator[dict[str, str]]:
    if provider != "auto":
        order = [provider]
    elif _is_large_request(messages):
        order = [
            "groq",
            "sambanova",
            "openrouter",
            "mistral",
            "cerebras",
            "groq_fast",
        ]
    else:
        order = [
            "groq_fast",
            "groq",
            "sambanova",
            "openrouter",
            "mistral",
            "cerebras",
        ]

    errors: list[str] = []

    for name in order:
        if name == "gemini":
            continue
        if not _provider_is_available(name):
            errors.append(f"{name}: cooling down")
            continue

        emitted = False
        try:
            async for token in _stream_openai_compatible(
                name=name,
                messages=messages,
                settings=settings,
                web_context=web_context,
                require_current=require_current,
                as_of=as_of,
            ):
                if not emitted:
                    emitted = True
                    yield {"type": "provider", "provider": name}
                yield {"type": "token", "token": token}

            if emitted:
                _clear_provider_failure(name)
                return
            raise RuntimeError("Provider returned an empty stream")
        except Exception as exc:
            _mark_provider_failure(name, exc, settings)
            errors.append(f"{name}: {exc}")
            if emitted:
                raise

    raise RuntimeError("All streaming providers failed. " + " | ".join(errors))
