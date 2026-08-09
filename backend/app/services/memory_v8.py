from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.services import personal_memory as legacy
from app.services import rag

_original_get_memory_enabled = legacy.get_memory_enabled
_original_list_user_memories = legacy.list_user_memories
_original_create_user_memory = legacy.create_user_memory


def normalize_memory_text(value: str) -> str:
    value = legacy.clean_memory_text(value)
    return re.sub(r"\s+", " ", value).strip().casefold()


async def _embed_memory(text: str, settings: Settings) -> list[float] | None:
    try:
        vectors = await rag._embed_batch(
            [text[:12000]],
            settings,
            task_type="RETRIEVAL_DOCUMENT",
            title="Personal memory",
        )
        return vectors[0] if vectors else None
    except Exception:
        return None


async def list_user_memories_v8(
    user_id: str,
    settings: Settings,
    *,
    limit: int = 50,
    user_jwt: str | None = None,
) -> list[dict[str, Any]]:
    if not legacy._configured(settings):
        return []

    safe_limit = max(1, min(int(limit), 100))
    url = (
        f"{legacy._base_url(settings)}/rest/v1/user_memories"
        f"?user_id=eq.{quote(user_id)}"
        "&select=id,memory_text,category,confidence,source,normalized_text,created_at,updated_at"
        "&order=updated_at.desc"
        f"&limit={safe_limit}"
    )
    try:
        async with httpx.AsyncClient(timeout=7.0) as client:
            response = await client.get(
                url,
                headers=legacy._headers(settings, user_jwt=user_jwt),
            )
        if response.status_code in {400, 404}:
            return await _original_list_user_memories(
                user_id, settings, limit=safe_limit, user_jwt=user_jwt
            )
        response.raise_for_status()
        rows = response.json()
        return rows if isinstance(rows, list) else []
    except Exception:
        return await _original_list_user_memories(
            user_id, settings, limit=safe_limit, user_jwt=user_jwt
        )


async def create_user_memory_v8(
    user_id: str,
    memory_text: str,
    settings: Settings,
    *,
    category: str = "preference",
    user_jwt: str | None = None,
    source: str = "explicit",
    confidence: float = 1.0,
) -> dict[str, Any]:
    if not legacy._configured(settings):
        raise RuntimeError("Supabase server credentials are not configured.")

    cleaned = legacy.clean_memory_text(memory_text)
    if len(cleaned) < 3:
        raise ValueError("Memory must contain at least 3 characters.")
    if legacy._contains_private_data(cleaned):
        raise ValueError(
            "Passwords, API keys, OTPs, phone numbers and other sensitive "
            "information cannot be saved as memory."
        )

    safe_source = str(source or "explicit").strip().casefold()
    safe_confidence = max(0.0, min(float(confidence), 1.0))
    if safe_source not in {"explicit", "manual"} or safe_confidence < 0.85:
        raise ValueError(
            "Only explicit/high-confidence user facts can be stored permanently."
        )

    normalized = normalize_memory_text(cleaned)
    existing = await list_user_memories_v8(
        user_id, settings, limit=100, user_jwt=user_jwt
    )
    for row in existing:
        old_norm = str(row.get("normalized_text") or "").strip().casefold()
        if not old_norm:
            old_norm = normalize_memory_text(str(row.get("memory_text") or ""))
        if old_norm == normalized:
            return {**row, "deduplicated": True}

    embedding = await _embed_memory(cleaned, settings)
    payload: dict[str, Any] = {
        "user_id": user_id,
        "memory_text": cleaned,
        "category": legacy.clean_memory_text(category)[:40] or "preference",
        "confidence": safe_confidence,
        "source": safe_source,
        "normalized_text": normalized,
    }
    if embedding is not None:
        payload["embedding"] = embedding

    url = f"{legacy._base_url(settings)}/rest/v1/user_memories"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            url,
            headers=legacy._headers(
                settings, representation=True, user_jwt=user_jwt
            ),
            json=payload,
        )

    if response.status_code in {400, 404} and (
        "column" in response.text.casefold()
        or "schema cache" in response.text.casefold()
    ):
        return await _original_create_user_memory(
            user_id,
            cleaned,
            settings,
            category=category,
            user_jwt=user_jwt,
        )

    if response.status_code == 409:
        rows = await list_user_memories_v8(
            user_id, settings, limit=100, user_jwt=user_jwt
        )
        for row in rows:
            if normalize_memory_text(str(row.get("memory_text") or "")) == normalized:
                return {**row, "deduplicated": True}
        raise ValueError("This memory is already saved.")

    response.raise_for_status()
    rows = response.json()
    if isinstance(rows, list) and rows:
        return rows[0]
    return payload


def _lexical_score(query: str, memory: str) -> float:
    q = {x for x in re.findall(r"[\w-]+", query.casefold()) if len(x) > 2}
    m = {x for x in re.findall(r"[\w-]+", memory.casefold()) if len(x) > 2}
    if not q or not m:
        return 0.0
    return len(q & m) / max(1, len(q))


async def search_relevant_memories(
    user_id: str,
    query: str,
    settings: Settings,
    *,
    match_count: int = 6,
    user_jwt: str | None = None,
) -> list[dict[str, Any]]:
    if not await _original_get_memory_enabled(
        user_id, settings, user_jwt=user_jwt
    ):
        return []

    query = str(query or "").strip()
    safe_count = max(1, min(int(match_count), 10))

    if query and settings.google_gemini_api:
        try:
            vector = await rag.embed_query(query, settings)
            url = f"{legacy._base_url(settings)}/rest/v1/rpc/match_user_memories"
            payload = {
                "p_user_id": user_id,
                "p_query_embedding": vector,
                "p_match_count": safe_count,
                "p_min_similarity": 0.30,
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url, headers=legacy._headers(settings), json=payload
                )
            if response.is_success:
                rows = response.json()
                if isinstance(rows, list) and rows:
                    return rows
        except Exception:
            pass

    rows = await list_user_memories_v8(
        user_id, settings, limit=30, user_jwt=user_jwt
    )
    if not query:
        return rows[:safe_count]

    ranked = []
    for row in rows:
        score = _lexical_score(query, str(row.get("memory_text") or ""))
        if score > 0:
            ranked.append(({**row, "similarity": score}, score))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return [item[0] for item in ranked[:safe_count]]


async def personal_memory_context_v8(
    user_id: str,
    settings: Settings,
    *,
    query: str = "",
    user_jwt: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    rows = await search_relevant_memories(
        user_id,
        query,
        settings,
        match_count=6,
        user_jwt=user_jwt,
    )
    if not rows:
        return "", []

    lines = [
        "RELEVANT PRIVATE USER MEMORY:",
        "Use only when directly relevant to the current request. "
        "Never expose database/internal implementation details.",
    ]
    for index, row in enumerate(rows, 1):
        confidence = float(row.get("confidence") or 1.0)
        lines.append(
            f"[MEMORY {index} | confidence={confidence:.2f}] "
            f"{str(row.get('memory_text') or '').strip()}"
        )
    return "\n".join(lines), rows
