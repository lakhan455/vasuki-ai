from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.config import Settings
from app.services.chat_v5 import build_resume_messages
from app.services.chat_v7 import route_chat_stream_v7
from app.services.omniroute_gateway_v10 import (
    configured as omniroute_configured,
    mark_fallback,
    stream_chat as omniroute_stream_chat,
)
from app.services.omniroute_knowledge_v10 import omniroute_context
from app.services.router_v7 import classify_route, last_user_query


def _join_context(*parts: str) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


async def route_chat_stream_v10(
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
    query = last_user_query(messages)
    decision = classify_route(messages, require_current=require_current)

    knowledge = ""
    if bool(getattr(settings, "omniroute_knowledge_enabled", True)):
        knowledge = omniroute_context(query, limit=4, max_chars=9000)

    enriched_context = _join_context(web_context, knowledge)

    # Respect an explicitly selected Vasuki provider.
    if provider != "auto":
        async for event in route_chat_stream_v7(
            provider,
            messages,
            settings,
            enriched_context,
            require_current=require_current,
            as_of=as_of,
            cache_bypass=cache_bypass,
            exclude_provider=exclude_provider,
        ):
            yield event
        return

    if not omniroute_configured(settings):
        async for event in route_chat_stream_v7(
            provider,
            messages,
            settings,
            enriched_context,
            require_current=require_current,
            as_of=as_of,
            cache_bypass=cache_bypass,
            exclude_provider=exclude_provider,
        ):
            yield event
        return

    complete = ""
    gateway_provider = ""
    try:
        async for event in omniroute_stream_chat(
            messages,
            settings,
            enriched_context,
            task_type=decision.task_type,
            require_current=require_current,
            cache_bypass=cache_bypass,
        ):
            event_type = event.get("type")
            if event_type == "provider":
                gateway_provider = event.get("provider", "")
            elif event_type == "token":
                complete += event.get("token", "")
            yield event
        return
    except Exception as exc:
        reason = f"{type(exc).__name__}: {str(exc)[:500]}"
        mark_fallback(reason)
        yield {
            "type": "diagnostic",
            "provider": gateway_provider or "omniroute",
            "status": "gateway_failed_fallback_to_vasuki",
            "error": str(exc)[:700],
        }

    # If OmniRoute streamed a partial answer before failing, resume locally instead
    # of restarting from scratch and duplicating text.
    fallback_messages = build_resume_messages(messages, complete) if complete.strip() else messages

    async for event in route_chat_stream_v7(
        "auto",
        fallback_messages,
        settings,
        enriched_context,
        require_current=require_current,
        as_of=as_of,
        cache_bypass=True if complete.strip() else cache_bypass,
        exclude_provider=exclude_provider,
    ):
        yield event


async def route_chat_v10(
    provider: str,
    messages: list[dict[str, Any]],
    settings: Settings,
    web_context: str = "",
    *,
    require_current: bool = False,
    as_of: str | None = None,
) -> tuple[str, str]:
    answer = ""
    provider_name = ""

    async for event in route_chat_stream_v10(
        provider,
        messages,
        settings,
        web_context,
        require_current=require_current,
        as_of=as_of,
    ):
        if event.get("type") == "provider":
            provider_name = event.get("provider", "")
        elif event.get("type") == "token":
            answer += event.get("token", "")

    if not answer.strip():
        raise RuntimeError("Vasuki V10 routing returned an empty answer.")
    return answer.strip(), provider_name or "auto"
