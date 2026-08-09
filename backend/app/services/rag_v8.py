from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings
from app.services import rag as legacy


async def search_user_documents_hybrid(
    *,
    user_id: str,
    query: str,
    document_ids: list[str] | None,
    settings: Settings,
    match_count: int = 8,
) -> list[dict[str, Any]]:
    if not legacy._configured(settings):
        return []

    safe_ids = legacy._safe_document_ids(document_ids)
    vector = await legacy.embed_query(query, settings)
    payload = {
        "p_user_id": user_id,
        "p_query_text": str(query or "")[:5000],
        "p_query_embedding": vector,
        "p_match_count": max(1, min(int(match_count), 15)),
        "p_document_ids": safe_ids or None,
    }
    url = (
        f"{legacy._base_url(settings)}/rest/v1/rpc/"
        "match_user_document_chunks_hybrid"
    )

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(
                url, headers=legacy._headers(settings), json=payload
            )
        if response.is_success:
            rows = response.json()
            if isinstance(rows, list):
                return rows
    except Exception:
        pass

    return await legacy.search_user_documents(
        user_id=user_id,
        query=query,
        document_ids=document_ids,
        settings=settings,
        match_count=match_count,
    )
