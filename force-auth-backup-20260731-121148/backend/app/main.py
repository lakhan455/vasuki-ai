from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.schemas import ChatRequest, ChatResponse, ImageRequest, ResearchRequest
from app.services.chat import route_chat
from app.services.context import compact_messages
from app.services.image import route_image
from app.services.ocr import extract_text
from app.services.research import (
    INDIA_STATES,
    is_all_india_state_cm_query,
    needs_live_web,
    search_web,
)

settings = get_settings()
app = FastAPI(title=settings.app_name, version="2.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _current_date() -> str:
    india_timezone = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(india_timezone).date().isoformat()


@app.get("/")
async def root() -> dict:
    return {
        "name": settings.app_name,
        "status": "online",
        "docs": "/docs",
        "version": "2.1.0",
        "truth_guard": "enabled",
        "smart_context": "enabled",
        "large_code": "enabled",
    }


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "environment": settings.app_env,
        "truth_guard": True,
        "smart_context": True,
        "large_code": True,
        "max_context_chars": settings.max_context_chars,
        "max_output_tokens": settings.max_output_tokens,
        "max_continuations": settings.max_continuations,
    }


@app.post("/api/research")
async def research(request: ResearchRequest) -> dict:
    current_date = _current_date()
    require_current = needs_live_web(request.query)
    results, provider = await search_web(
        request.query,
        settings,
        request.max_results,
        require_current=require_current,
        as_of=current_date,
    )
    return {
        "results": results,
        "provider": provider,
        "as_of": current_date,
        "live_verification": require_current,
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    raw_messages = [item.model_dump() for item in request.messages]

    query = next(
        (
            item["content"]
            for item in reversed(raw_messages)
            if item["role"] == "user"
        ),
        "",
    )
    current_date = _current_date()

    # Accuracy-first: factual/current questions always use live evidence,
    # even if the UI web toggle is off.
    require_current = needs_live_web(query)
    should_search = request.use_web or require_current

    sources: list[dict] = []
    web_context = ""

    if should_search:
        max_results = 12 if require_current else 8
        sources, search_provider = await search_web(
            query,
            settings,
            max_results,
            require_current=require_current,
            as_of=current_date,
        )

        if require_current and not sources:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Live verification was required, but no reliable evidence "
                    "was returned. The AI refused to guess from old model memory. "
                    f"Search status: {search_provider}"
                ),
            )

        if is_all_india_state_cm_query(query):
            found_entities = {
                str(item.get("entity") or "").casefold()
                for item in sources
            }
            missing = [
                state
                for state in INDIA_STATES
                if state.casefold() not in found_entities
            ]
            if missing:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "The complete Chief Minister list could not be safely "
                        "verified because live evidence was missing for: "
                        + ", ".join(missing)
                    ),
                )

        if sources:
            context_parts: list[str] = []
            for index, source in enumerate(sources, 1):
                published = source.get("published_date") or "not provided"
                entity = source.get("entity") or "general"
                source_type = source.get("source_type") or "other"
                context_parts.append(
                    f"[{index}] ENTITY: {entity}\n"
                    f"SOURCE TYPE: {source_type}\n"
                    f"TITLE: {source.get('title', 'Source')}\n"
                    f"URL: {source.get('url', '')}\n"
                    f"PUBLISHED/UPDATED: {published}\n"
                    f"CONTENT:\n{source.get('content', '')}"
                )
            web_context = "\n\n".join(context_parts)

    # Never reject a long chat. Keep recent turns automatically and reserve
    # room for the system prompt, live evidence and the model response.
    available_message_chars = max(
        8000,
        settings.max_context_chars
        - len(web_context)
        - settings.context_reserve_chars,
    )
    messages, context_stats = compact_messages(
        raw_messages,
        max_chars=available_message_chars,
        max_single_message_chars=settings.max_single_message_chars,
    )

    try:
        answer, provider = await route_chat(
            request.provider,
            messages,
            settings,
            web_context,
            require_current=require_current,
            as_of=current_date,
        )
        return ChatResponse(
            answer=answer,
            provider=provider,
            sources=sources,
            context_trimmed=context_stats.trimmed,
            original_context_chars=context_stats.original_chars,
            used_context_chars=context_stats.used_chars,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/image")
async def generate_image(request: ImageRequest) -> dict:
    try:
        return await route_image(request.provider, request.prompt, settings)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/ocr")
async def ocr(file: UploadFile = File(...)) -> dict:
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File must be under 10 MB")

    try:
        return await extract_text(file, settings)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
