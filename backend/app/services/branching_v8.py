from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.services.analytics_v8 import _base, _headers, configured


async def create_branch(
    settings: Settings,
    *,
    user_id: str,
    conversation_id: str,
    source_message_id: str | None,
    original_prompt: str,
    edited_prompt: str,
    note: str | None = None,
) -> dict[str, Any]:
    if not configured(settings):
        raise RuntimeError('Supabase is not configured.')
    payload = {
        'id': str(uuid.uuid4()),
        'user_id': user_id,
        'conversation_id': str(conversation_id)[:120],
        'source_message_id': str(source_message_id or '')[:120] or None,
        'original_prompt': str(original_prompt or '')[:12000],
        'edited_prompt': str(edited_prompt or '')[:12000],
        'note': str(note or '')[:2000] or None,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{_base(settings)}/rest/v1/conversation_branches",
            headers=_headers(settings, representation=True),
            json=payload,
        )
    response.raise_for_status()
    rows = response.json()
    if isinstance(rows, list) and rows:
        return rows[0]
    return payload


async def list_branches(settings: Settings, *, user_id: str, conversation_id: str) -> list[dict[str, Any]]:
    if not configured(settings):
        return []
    url = (
        f"{_base(settings)}/rest/v1/conversation_branches"
        f"?user_id=eq.{quote(user_id)}&conversation_id=eq.{quote(conversation_id)}"
        "&select=id,conversation_id,source_message_id,original_prompt,edited_prompt,note,created_at"
        "&order=created_at.desc"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=_headers(settings))
    response.raise_for_status()
    rows = response.json()
    return rows if isinstance(rows, list) else []
