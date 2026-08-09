from __future__ import annotations

import asyncio
from typing import Any

from fastapi import Depends

import app.main as legacy
import app.main_v6 as v6
import app.main_v7 as v7
from app.auth import AuthUser, get_current_user
from app.services import personal_memory as memory_service
from app.services.context_v8 import compact_messages_v8
from app.services.memory_v8 import (
    create_user_memory_v8,
    list_user_memories_v8,
    personal_memory_context_v8,
)
from app.services.rag_v8 import search_user_documents_hybrid

app = v7.app
settings = v7.settings

legacy.compact_messages = compact_messages_v8
legacy.create_user_memory = create_user_memory_v8
legacy.list_user_memories = list_user_memories_v8
memory_service.create_user_memory = create_user_memory_v8
memory_service.list_user_memories = list_user_memories_v8


async def _private_context_v8(
    *,
    user_id: str,
    access_token: str,
    query: str,
    request,
) -> tuple[str, list[dict[str, Any]]]:
    personal_pack = ""
    document_pack = ""
    document_sources: list[dict[str, Any]] = []

    if request.use_memory:
        try:
            personal_pack, _ = await asyncio.wait_for(
                personal_memory_context_v8(
                    user_id,
                    settings,
                    query=query,
                    user_jwt=access_token,
                ),
                timeout=3.5,
            )
        except Exception:
            personal_pack = ""

    if request.use_documents:
        try:
            hits = await asyncio.wait_for(
                search_user_documents_hybrid(
                    user_id=user_id,
                    query=query,
                    document_ids=request.document_ids,
                    settings=settings,
                    match_count=settings.document_match_count,
                ),
                timeout=18.0,
            )
            document_pack, document_sources = legacy.document_context(hits)
        except Exception:
            document_pack, document_sources = "", []

    return legacy._join_context(personal_pack, document_pack), document_sources


legacy._private_context = _private_context_v8


async def _puter_memory_context(user_id, app_settings, *, user_jwt=None):
    return await personal_memory_context_v8(
        user_id, app_settings, query="", user_jwt=user_jwt
    )


v6.personal_memory_context = _puter_memory_context


@app.get("/api/diagnostics/v8-foundation")
async def diagnostics_v8(
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v8-foundation",
        "semantic_personal_memory": True,
        "memory_confidence": True,
        "memory_deduplication": True,
        "hybrid_document_search": True,
        "conversation_compression": "project_state_plus_latest_8",
        "migration_safe_fallback": True,
        "user_id_suffix": current_user.id[-6:],
    }


@app.get("/health/v8")
async def health_v8() -> dict[str, Any]:
    return {
        "ok": True,
        "service": settings.app_name,
        "version": "v8-foundation",
        "router": "v7-compatible",
        "semantic_memory": True,
        "hybrid_rag": True,
        "truth_guard": True,
    }
