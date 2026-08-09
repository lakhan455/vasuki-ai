from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.services.analytics_v8 import _base, _headers, configured


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\w-]+", str(value or "").casefold())
        if len(token) > 1
    }


def _score(query: str, title: str, text: str) -> float:
    q = _tokens(query)
    if not q:
        return 0.0
    title_low = title.casefold()
    text_low = text.casefold()
    query_low = query.casefold()
    score = 0.0
    if query_low in title_low:
        score += 5.0
    if query_low in text_low:
        score += 3.0
    score += 2.0 * len(q & _tokens(title)) / max(1, len(q))
    score += 1.0 * len(q & _tokens(text)) / max(1, len(q))
    return score


async def search_chat_history(
    settings: Settings,
    *,
    user_id: str,
    query: str,
    limit: int = 24,
) -> list[dict[str, Any]]:
    if not configured(settings):
        return []
    clean = re.sub(r"\s+", " ", str(query or "")).strip()
    if len(clean) < 2:
        return []
    safe_limit = max(1, min(int(limit), 50))

    chats_url = (
        f"{_base(settings)}/rest/v1/user_chats"
        f"?user_id=eq.{quote(user_id)}"
        "&select=id,title,updated_at,project_id,messages"
        "&order=updated_at.desc&limit=160"
    )
    messages_url = (
        f"{_base(settings)}/rest/v1/user_chat_messages"
        f"?user_id=eq.{quote(user_id)}"
        "&select=chat_id,role,content,updated_at"
        "&order=updated_at.desc&limit=700"
    )

    async with httpx.AsyncClient(timeout=12.0) as client:
        chats_response, messages_response = await asyncio.gather(
            client.get(chats_url, headers=_headers(settings)),
            client.get(messages_url, headers=_headers(settings)),
        )

    chats_response.raise_for_status()
    chats = chats_response.json()
    chats = chats if isinstance(chats, list) else []

    messages: list[dict[str, Any]] = []
    if messages_response.is_success:
        raw = messages_response.json()
        messages = raw if isinstance(raw, list) else []

    by_chat: dict[str, list[str]] = {}
    for row in messages:
        chat_id = str(row.get("chat_id") or "")
        content = str(row.get("content") or "").strip()
        if chat_id and content:
            by_chat.setdefault(chat_id, []).append(content)

    ranked: list[tuple[dict[str, Any], float]] = []
    for chat in chats:
        chat_id = str(chat.get("id") or "")
        title = str(chat.get("title") or "New Chat")
        body_parts = by_chat.get(chat_id, [])
        if not body_parts:
            fallback = chat.get("messages")
            if isinstance(fallback, list):
                body_parts = [
                    str(item.get("content") or "")
                    for item in fallback
                    if isinstance(item, dict)
                ]
        body = "\n".join(body_parts[:80])
        score = _score(clean, title, body)
        if score <= 0:
            continue

        snippet = ""
        query_low = clean.casefold()
        for part in body_parts:
            if query_low in part.casefold() or (_tokens(clean) & _tokens(part)):
                snippet = re.sub(r"\s+", " ", part).strip()[:280]
                break
        if not snippet and body_parts:
            snippet = re.sub(r"\s+", " ", body_parts[0]).strip()[:280]

        ranked.append(
            (
                {
                    "chat_id": chat_id,
                    "title": title,
                    "snippet": snippet,
                    "updated_at": chat.get("updated_at"),
                    "project_id": chat.get("project_id"),
                    "score": round(score, 4),
                },
                score,
            )
        )

    ranked.sort(key=lambda item: item[1], reverse=True)
    return [item[0] for item in ranked[:safe_limit]]


async def list_recent_branches_all(
    settings: Settings,
    *,
    user_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if not configured(settings):
        return []
    safe_limit = max(1, min(int(limit), 200))
    url = (
        f"{_base(settings)}/rest/v1/conversation_branches"
        f"?user_id=eq.{quote(user_id)}"
        "&select=id,conversation_id,source_message_id,original_prompt,edited_prompt,note,created_at"
        "&order=created_at.desc"
        f"&limit={safe_limit}"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=_headers(settings))
    response.raise_for_status()
    rows = response.json()
    return rows if isinstance(rows, list) else []
