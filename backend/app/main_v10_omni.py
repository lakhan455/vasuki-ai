from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Query

import app.main as legacy
import app.main_v5 as v5
import app.main_v9_phase6 as phase6
import app.services.rag as rag
from app.auth import AuthUser, get_current_user
from app.services.chat_v10 import route_chat_stream_v10, route_chat_v10
from app.services.embedding_v10 import embed_batch_v10
from app.services.image_v10 import route_image_v10
from app.services.omniroute_gateway_v10 import (
    configured as omniroute_configured,
    probe as omniroute_probe,
    search_web as omniroute_search_web,
    snapshot as omniroute_snapshot,
)
from app.services.omniroute_knowledge_v10 import (
    corpus_info,
    search_omniroute_knowledge,
)
from app.services.plans_v2 import get_plan_status

app = phase6.app
settings = phase6.settings

# Keep references to Vasuki's pre-V10 fallbacks before monkeypatching.
_v9_embed_batch = rag._embed_batch
_v9_rag_configured = rag._configured
_v9_search_web = legacy.search_web

# Route both synchronous and streaming chat through V10.
legacy.route_chat = route_chat_v10
v5.route_chat_stream_v5 = route_chat_stream_v10

# Route automatic image generation through OmniRoute when explicitly enabled,
# with Vasuki's existing image router as fallback.
legacy.route_image = route_image_v10

# Allow OmniRoute embeddings while retaining Gemini as fallback.
async def _embed_batch_v10_adapter(
    texts: list[str],
    settings_arg,
    *,
    task_type: str,
    title: str | None = None,
):
    return await embed_batch_v10(
        texts,
        settings_arg,
        task_type=task_type,
        title=title,
        fallback=_v9_embed_batch,
    )

rag._embed_batch = _embed_batch_v10_adapter

def _rag_configured_v10(settings_arg) -> bool:
    if _v9_rag_configured(settings_arg):
        return True
    return bool(
        getattr(settings_arg, "supabase_url", None)
        and (
            getattr(settings_arg, "supabase_secret_key", None)
            or getattr(settings_arg, "supabase_service_role_key", None)
        )
        and omniroute_configured(settings_arg)
        and bool(getattr(settings_arg, "omniroute_embedding_enabled", False))
        and str(getattr(settings_arg, "omniroute_embedding_model", "") or "").strip()
    )

rag._configured = _rag_configured_v10


async def _search_web_v10(
    query: str,
    settings_arg,
    max_results: int = 10,
    *,
    require_current: bool = False,
    as_of: str | None = None,
):
    existing_results = []
    existing_provider = ""
    existing_error = None
    try:
        existing_results, existing_provider = await _v9_search_web(
            query,
            settings_arg,
            max_results,
            require_current=require_current,
            as_of=as_of,
        )
    except Exception as exc:
        existing_error = exc

    use_omni = (
        omniroute_configured(settings_arg)
        and bool(getattr(settings_arg, "omniroute_search_enabled", False))
    )
    if not use_omni:
        if existing_error and not existing_results:
            raise existing_error
        return existing_results, existing_provider

    # Preserve Vasuki's specialized research router, then supplement it when
    # evidence is sparse or unavailable.
    need_more = len(existing_results) < min(max_results, 4)
    if not need_more:
        return existing_results, existing_provider

    try:
        omni_results, omni_provider = await omniroute_search_web(
            query,
            settings_arg,
            max_results=max_results,
            require_current=require_current,
        )
    except Exception:
        if existing_error and not existing_results:
            raise existing_error
        return existing_results, existing_provider

    merged = []
    seen = set()
    for item in [*existing_results, *omni_results]:
        url = str(item.get("url") or "").strip() if isinstance(item, dict) else ""
        key = url.casefold() if url else str(item)[:200].casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
        if len(merged) >= max_results:
            break

    provider = "+".join(part for part in [existing_provider, omni_provider] if part)
    return merged, provider or "omniroute-search"


legacy.search_web = _search_web_v10


async def _require_owner(current_user: AuthUser) -> None:
    status = await get_plan_status(current_user, settings)
    if not status.is_owner:
        raise HTTPException(status_code=403, detail="Owner access required.")


@app.get("/api/omni/v10/knowledge")
async def omni_knowledge_info(
    _current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {"ok": True, "knowledge": corpus_info()}


@app.get("/api/omni/v10/knowledge/search")
async def omni_knowledge_search(
    q: str = Query(..., min_length=2, max_length=500),
    limit: int = Query(5, ge=1, le=10),
    _current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "ok": True,
        "query": q,
        "results": search_omniroute_knowledge(q, limit=limit),
    }


@app.get("/api/owner/omni/v10")
async def owner_omni_status(
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    await _require_owner(current_user)
    return {
        "ok": True,
        "gateway": await omniroute_probe(settings),
        "telemetry": omniroute_snapshot(),
        "knowledge": corpus_info(),
        "routing": {
            "automatic": True,
            "profiles": {
                "simple": "auto/fast",
                "general": "auto",
                "code": "auto/coding:reliable",
                "reasoning": "auto/reasoning:reliable",
                "research_current": "auto/reasoning:reliable",
            },
            "fallback": "existing Vasuki V9/V7 provider router",
        },
        "gateway_capabilities_from_source": {
            "chat_completions": "/v1/chat/completions",
            "embeddings": "/v1/embeddings",
            "images": "/v1/images/generations",
            "mcp": "available in OmniRoute runtime when enabled/configured",
            "a2a": "available in OmniRoute runtime when enabled/configured",
        },
    }


@app.get("/health/v10-omni")
async def health_v10_omni() -> dict[str, Any]:
    knowledge = corpus_info()
    return {
        "ok": True,
        "version": "v10-omni-brain",
        "omniroute_gateway_enabled": bool(getattr(settings, "omniroute_enabled", False)),
        "omniroute_gateway_configured": omniroute_configured(settings),
        "omniroute_knowledge": bool(knowledge.get("available")),
        "omniroute_knowledge_chunks": int(knowledge.get("chunks") or 0),
        "smart_auto_routing": True,
        "gateway_chat": True,
        "gateway_image": bool(getattr(settings, "omniroute_image_enabled", False)),
        "gateway_embeddings": bool(getattr(settings, "omniroute_embedding_enabled", False)),
        "gateway_search": bool(getattr(settings, "omniroute_search_enabled", False)),
        "automatic_vasuki_fallback": True,
        "source_version": knowledge.get("source_version") or "3.8.50",
        "note": (
            "Full OmniRoute provider/combo/circuit-breaker/quota/cost routing becomes active "
            "when a separate OmniRoute runtime is reachable through OMNIROUTE_BASE_URL. "
            "Until then Vasuki keeps its existing provider router while the source-derived "
            "OmniRoute knowledge corpus remains available."
        ),
    }
