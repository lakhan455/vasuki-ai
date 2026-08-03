from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.auth import AuthUser, get_current_user
from app.config import get_settings
from app.schemas import (
    ChatRequest,
    ChatResponse,
    ImageRequest,
    MemoryCreateRequest,
    MemorySettingsRequest,
    ResearchRequest,
)
from app.services.chat import route_chat, route_chat_stream
from app.services.context import compact_messages
from app.services.image import route_image
from app.services.identity import fixed_identity_reply
from app.services.knowledge import (
    extract_correction,
    find_verified_knowledge,
    hit_sources,
    is_direct_fact_question,
    knowledge_context,
    learn_from_correction,
)
from app.services.ocr import extract_text
from app.services.personal_memory import (
    create_user_memory,
    delete_user_memory,
    extract_explicit_memory,
    get_memory_enabled,
    list_user_memories,
    personal_memory_context,
    set_memory_enabled,
)
from app.services.rag import (
    delete_user_document,
    document_context,
    ingest_user_document,
    list_user_documents,
    search_user_documents,
)
from app.services.research import (
    INDIA_STATES,
    is_all_india_state_cm_query,
    needs_live_web,
    search_web,
)
from app.services.vision import process_vision_request


settings = get_settings()
app = FastAPI(title=settings.app_name, version="3.0.0")
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


def _join_context(*parts: str) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def _sse(event: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {encoded}\n\n"


def _direct_stream(
    answer: str,
    *,
    provider: str,
    sources: list[dict[str, Any]] | None = None,
) -> StreamingResponse:
    async def generate():
        yield _sse("token", {"token": answer})
        yield _sse(
            "meta",
            {
                "provider": provider,
                "sources": sources or [],
                "done": True,
            },
        )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _private_context(
    *,
    user_id: str,
    access_token: str,
    query: str,
    request: ChatRequest,
) -> tuple[str, list[dict[str, Any]]]:
    personal_pack = ""
    document_pack = ""
    document_sources: list[dict[str, Any]] = []

    if request.use_memory:
        try:
            personal_pack, _memory_rows = await asyncio.wait_for(
                personal_memory_context(
                    user_id,
                    settings,
                    user_jwt=access_token,
                ),
                timeout=4.0,
            )
        except Exception:
            personal_pack = ""

    if request.use_documents:
        try:
            hits = await asyncio.wait_for(
                search_user_documents(
                    user_id=user_id,
                    query=query,
                    document_ids=request.document_ids,
                    settings=settings,
                    match_count=settings.document_match_count,
                ),
                timeout=18.0,
            )
            document_pack, document_sources = document_context(hits)
        except Exception:
            document_pack, document_sources = "", []

    return _join_context(personal_pack, document_pack), document_sources


async def _shared_knowledge(
    query: str,
) -> tuple[list, list, str]:
    try:
        memory_hits = await asyncio.wait_for(
            find_verified_knowledge(query, settings),
            timeout=1.2,
        )
    except Exception:
        memory_hits = []

    strong_memory_hits = [
        hit
        for hit in memory_hits
        if hit.score >= settings.global_memory_direct_answer_score
        and hit.confidence >= 0.72
    ]
    return (
        strong_memory_hits,
        hit_sources(strong_memory_hits),
        knowledge_context(strong_memory_hits),
    )


async def _web_context(
    *,
    query: str,
    current_date: str,
    request: ChatRequest,
) -> tuple[bool, list[dict[str, Any]], str]:
    require_current = needs_live_web(query)
    should_search = request.use_web or require_current

    if not should_search:
        return require_current, [], ""

    max_results = 8 if require_current else 4
    try:
        sources, _provider = await asyncio.wait_for(
            search_web(
                query,
                settings,
                max_results,
                require_current=require_current,
                as_of=current_date,
            ),
            timeout=min(float(settings.web_search_timeout_seconds), 18.0),
        )
    except Exception:
        sources = []

    if not sources:
        return require_current, [], ""

    parts: list[str] = []
    for index, source in enumerate(sources, 1):
        parts.append(
            f"[{index}] ENTITY: {source.get('entity') or 'general'}\n"
            f"SOURCE TYPE: {source.get('source_type') or 'other'}\n"
            f"TITLE: {source.get('title', 'Source')}\n"
            f"URL: {source.get('url', '')}\n"
            f"PUBLISHED/UPDATED: "
            f"{source.get('published_date') or 'not provided'}\n"
            f"CONTENT:\n{source.get('content', '')}"
        )

    return require_current, sources, "\n\n".join(parts)


def _missing_state_evidence(
    query: str,
    sources: list[dict[str, Any]],
) -> list[str]:
    if not is_all_india_state_cm_query(query):
        return []

    found_entities = {
        str(item.get("entity") or "").casefold()
        for item in sources
    }
    return [
        state
        for state in INDIA_STATES
        if state.casefold() not in found_entities
    ]


@app.get("/")
async def root() -> dict:
    return {
        "name": settings.app_name,
        "status": "online",
        "docs": "/docs",
        "version": "3.0.0",
        "truth_guard": "enabled",
        "smart_context": "enabled",
        "large_code": "enabled",
        "speed_guard": "enabled",
        "streaming": "enabled",
        "backend_auth": "enabled",
        "personal_memory": "enabled",
        "document_rag": "enabled",
        "global_learning": (
            "configured"
            if settings.global_learning_configured
            else "not_configured"
        ),
    }


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "environment": settings.app_env,
        "truth_guard": True,
        "smart_context": True,
        "large_code": True,
        "speed_guard": True,
        "streaming": True,
        "backend_auth": bool(
            settings.supabase_url
            and (
                settings.supabase_secret_key
                or settings.supabase_service_role_key
            )
        ),
        "personal_memory": True,
        "document_rag": bool(
            settings.google_gemini_api
            and settings.supabase_url
        ),
        "embedding_model": settings.gemini_embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "global_learning_enabled": settings.global_learning_enabled,
        "global_learning_configured": settings.global_learning_configured,
        "max_context_chars": settings.max_context_chars,
        "max_output_tokens": settings.max_output_tokens,
        "chat_timeout_seconds": settings.chat_timeout_seconds,
        "total_chat_timeout_seconds": settings.total_chat_timeout_seconds,
        "web_search_timeout_seconds": settings.web_search_timeout_seconds,
    }


@app.get("/api/knowledge/status")
async def knowledge_status() -> dict:
    return {
        "enabled": settings.global_learning_enabled,
        "configured": settings.global_learning_configured,
        "mode": "verified-shared-memory",
        "private_data_learning": False,
    }


@app.get("/api/memory")
async def memory_list(
    current_user: AuthUser = Depends(get_current_user),
) -> dict:
    enabled, memories = await asyncio.gather(
        get_memory_enabled(
            current_user.id,
            settings,
            user_jwt=current_user.access_token,
        ),
        list_user_memories(
            current_user.id,
            settings,
            user_jwt=current_user.access_token,
        ),
    )
    return {"enabled": enabled, "memories": memories}


@app.post("/api/memory")
async def memory_create(
    request: MemoryCreateRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict:
    try:
        memory = await create_user_memory(
            current_user.id,
            request.memory_text,
            settings,
            category=request.category,
            user_jwt=current_user.access_token,
        )
        return {"ok": True, "memory": memory}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Memory could not be saved: {str(exc)[:300]}",
        ) from exc


@app.patch("/api/memory/settings")
async def memory_settings(
    request: MemorySettingsRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict:
    try:
        enabled = await set_memory_enabled(
            current_user.id,
            request.enabled,
            settings,
            user_jwt=current_user.access_token,
        )
        return {"ok": True, "enabled": enabled}
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Memory settings could not be updated.",
        ) from exc


@app.delete("/api/memory/{memory_id}")
async def memory_delete(
    memory_id: str,
    current_user: AuthUser = Depends(get_current_user),
) -> dict:
    try:
        await delete_user_memory(
            current_user.id,
            memory_id,
            settings,
            user_jwt=current_user.access_token,
        )
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Memory could not be deleted.",
        ) from exc


@app.get("/api/documents")
async def documents_list(
    current_user: AuthUser = Depends(get_current_user),
) -> dict:
    documents = await list_user_documents(current_user.id, settings)
    return {"documents": documents}


@app.post("/api/documents")
async def documents_upload(
    file: UploadFile = File(...),
    current_user: AuthUser = Depends(get_current_user),
) -> dict:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded document is empty.")

    try:
        document = await ingest_user_document(
            user_id=current_user.id,
            filename=file.filename or "document.txt",
            mime_type=file.content_type or "application/octet-stream",
            content=content,
            settings=settings,
        )
        return {"ok": True, "document": document}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        detail = str(exc)[:1000]
        raise HTTPException(
            status_code=503,
            detail=detail or "Document processing failed.",
        ) from exc


@app.delete("/api/documents/{document_id}")
async def documents_delete(
    document_id: str,
    current_user: AuthUser = Depends(get_current_user),
) -> dict:
    try:
        await delete_user_document(
            current_user.id,
            document_id,
            settings,
        )
        return {"ok": True}
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid document ID.") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Document could not be deleted.",
        ) from exc


@app.post("/api/research")
async def research(
    request: ResearchRequest,
    _current_user: AuthUser = Depends(get_current_user),
) -> dict:
    current_date = _current_date()
    require_current = needs_live_web(request.query)

    try:
        results, provider = await asyncio.wait_for(
            search_web(
                request.query,
                settings,
                request.max_results,
                require_current=require_current,
                as_of=current_date,
            ),
            timeout=min(float(settings.web_search_timeout_seconds), 18.0),
        )
    except asyncio.TimeoutError:
        results, provider = [], "search-timeout"
    except Exception:
        results, provider = [], "search-unavailable"

    return {
        "results": results,
        "provider": provider,
        "as_of": current_date,
        "live_verification": require_current,
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: AuthUser = Depends(get_current_user),
) -> ChatResponse:
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
    original_chars = sum(len(item["content"]) for item in raw_messages)

    identity_answer = fixed_identity_reply(query)
    if identity_answer:
        return ChatResponse(
            answer=identity_answer,
            provider="vasuki-identity",
            sources=[],
            context_trimmed=False,
            original_context_chars=original_chars,
            used_context_chars=len(query),
        )

    explicit_memory = (
        extract_explicit_memory(query)
        if request.use_memory
        else None
    )
    if explicit_memory:
        try:
            await create_user_memory(
                current_user.id,
                explicit_memory,
                settings,
                user_jwt=current_user.access_token,
            )
            answer = f"Yaad rakh liya: {explicit_memory}"
        except ValueError as exc:
            answer = str(exc)
        except Exception as exc:
            print("[memory] save failed:", type(exc).__name__, str(exc)[:500])
            answer = "Memory save nahi ho paayi. Thodi der baad dobara try karein."

        return ChatResponse(
            answer=answer,
            provider="vasuki-personal-memory",
            sources=[],
            context_trimmed=False,
            original_context_chars=original_chars,
            used_context_chars=len(query),
        )

    correction = extract_correction(raw_messages)
    if correction and settings.global_learning_configured:
        background_tasks.add_task(
            learn_from_correction,
            raw_messages,
            settings,
            current_date,
        )
        return ChatResponse(
            answer=(
                "धन्यवाद। मैंने आपकी correction receive कर ली है। "
                "इसे live sources से verify करके shared Vasuki knowledge में "
                "save किया जाएगा। केवल verified जानकारी ही सभी users को दिखाई जाएगी।"
            ),
            provider="vasuki-learning",
            sources=[],
            context_trimmed=False,
            original_context_chars=original_chars,
            used_context_chars=len(query),
        )

    strong_hits, shared_sources, shared_pack = await _shared_knowledge(query)

    if (
        strong_hits
        and is_direct_fact_question(query)
        and not request.use_web
        and not request.use_documents
    ):
        best = strong_hits[0]
        return ChatResponse(
            answer=best.answer,
            provider="vasuki-global-memory",
            sources=shared_sources,
            context_trimmed=False,
            original_context_chars=original_chars,
            used_context_chars=len(query),
        )

    private_pack, document_sources = await _private_context(
        user_id=current_user.id,
        access_token=current_user.access_token,
        query=query,
        request=request,
    )
    require_current, web_sources, live_pack = await _web_context(
        query=query,
        current_date=current_date,
        request=request,
    )

    if require_current and not web_sources and not strong_hits:
        return ChatResponse(
            answer=(
                "Live verification service is temporarily unavailable. "
                "Please retry in a few seconds so I do not guess from old information."
            ),
            provider="truth-guard",
            sources=document_sources,
            context_trimmed=False,
            original_context_chars=original_chars,
            used_context_chars=len(query),
        )

    missing = _missing_state_evidence(query, web_sources)
    if missing:
        raise HTTPException(
            status_code=503,
            detail=(
                "The complete Chief Minister list could not be safely "
                "verified because evidence was missing for: "
                + ", ".join(missing)
            ),
        )

    web_context = _join_context(shared_pack, private_pack, live_pack)
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
        answer, provider = await asyncio.wait_for(
            route_chat(
                request.provider,
                messages,
                settings,
                web_context,
                require_current=require_current,
                as_of=current_date,
            ),
            timeout=min(float(settings.total_chat_timeout_seconds), 55.0),
        )
        return ChatResponse(
            answer=answer,
            provider=provider,
            sources=shared_sources + document_sources + web_sources,
            context_trimmed=context_stats.trimmed,
            original_context_chars=context_stats.original_chars,
            used_context_chars=context_stats.used_chars,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="The AI provider took too long to respond. Please retry.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "All configured AI providers are temporarily busy or unavailable. "
                "Please retry in a few seconds."
            ),
        ) from exc


@app.post("/api/chat/stream")
async def chat_stream(
    chat_request: ChatRequest,
    http_request: Request,
    current_user: AuthUser = Depends(get_current_user),
) -> StreamingResponse:
    raw_messages = [item.model_dump() for item in chat_request.messages]
    query = next(
        (
            item["content"]
            for item in reversed(raw_messages)
            if item["role"] == "user"
        ),
        "",
    )
    current_date = _current_date()

    identity_answer = fixed_identity_reply(query)
    if identity_answer:
        return _direct_stream(
            identity_answer,
            provider="vasuki-identity",
        )

    explicit_memory = (
        extract_explicit_memory(query)
        if chat_request.use_memory
        else None
    )
    if explicit_memory:
        try:
            await create_user_memory(
                current_user.id,
                explicit_memory,
                settings,
                user_jwt=current_user.access_token,
            )
            answer = f"Yaad rakh liya: {explicit_memory}"
        except ValueError as exc:
            answer = str(exc)
        except Exception as exc:
            print("[memory] save failed:", type(exc).__name__, str(exc)[:500])
            answer = "Memory save nahi ho paayi. Thodi der baad dobara try karein."
        return _direct_stream(
            answer,
            provider="vasuki-personal-memory",
        )

    strong_hits, shared_sources, shared_pack = await _shared_knowledge(query)

    if (
        strong_hits
        and is_direct_fact_question(query)
        and not chat_request.use_web
        and not chat_request.use_documents
    ):
        return _direct_stream(
            strong_hits[0].answer,
            provider="vasuki-global-memory",
            sources=shared_sources,
        )

    private_pack, document_sources = await _private_context(
        user_id=current_user.id,
        access_token=current_user.access_token,
        query=query,
        request=chat_request,
    )
    require_current, web_sources, live_pack = await _web_context(
        query=query,
        current_date=current_date,
        request=chat_request,
    )

    if require_current and not web_sources and not strong_hits:
        return _direct_stream(
            (
                "Live verification service is temporarily unavailable. "
                "Please retry in a few seconds so I do not guess from old information."
            ),
            provider="truth-guard",
            sources=document_sources,
        )

    missing = _missing_state_evidence(query, web_sources)
    if missing:
        return _direct_stream(
            (
                "The complete list could not be safely verified because live "
                "evidence was missing for: " + ", ".join(missing)
            ),
            provider="truth-guard",
            sources=web_sources,
        )

    web_context = _join_context(shared_pack, private_pack, live_pack)
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
    all_sources = shared_sources + document_sources + web_sources

    async def generate():
        provider_name = ""
        try:
            yield _sse(
                "ready",
                {
                    "context_trimmed": context_stats.trimmed,
                    "original_context_chars": context_stats.original_chars,
                    "used_context_chars": context_stats.used_chars,
                },
            )

            async for event in route_chat_stream(
                chat_request.provider,
                messages,
                settings,
                web_context,
                require_current=require_current,
                as_of=current_date,
            ):
                if await http_request.is_disconnected():
                    return

                if event.get("type") == "provider":
                    provider_name = event.get("provider", "")
                    yield _sse(
                        "provider",
                        {"provider": provider_name},
                    )
                elif event.get("type") == "token":
                    yield _sse(
                        "token",
                        {"token": event.get("token", "")},
                    )

            yield _sse(
                "meta",
                {
                    "provider": provider_name or "auto",
                    "sources": all_sources,
                    "context_trimmed": context_stats.trimmed,
                    "original_context_chars": context_stats.original_chars,
                    "used_context_chars": context_stats.used_chars,
                    "done": True,
                },
            )
        except asyncio.CancelledError:
            return
        except Exception as exc:
            yield _sse(
                "error",
                {
                    "detail": (
                        "AI streaming temporarily failed. Please retry once."
                    ),
                    "debug": str(exc)[:300]
                    if settings.app_env != "production"
                    else "",
                },
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/vision/status")
async def vision_status() -> dict:
    return {
        "ok": True,
        "gemini_vision_configured": bool(settings.google_gemini_api),
        "cloudflare_vision_configured": bool(
            settings.cloudflare_account_id
            and settings.cloudflare_workers_ai
        ),
        "ocr_configured": bool(settings.ocr_space_api),
        "gemini_vision_model": settings.gemini_vision_model,
        "gemini_image_edit_model": settings.gemini_image_edit_model,
        "cloudflare_vision_model": settings.cloudflare_vision_model,
        "cloudflare_edit_model": settings.cloudflare_edit_model,
        "max_file_mb": settings.vision_max_file_mb,
    }


@app.post("/api/vision")
async def vision(
    file: UploadFile = File(...),
    prompt: str = Form(""),
    operation: str = Form("auto"),
    _current_user: AuthUser = Depends(get_current_user),
) -> dict:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    max_bytes = int(settings.vision_max_file_mb) * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File must be {settings.vision_max_file_mb} MB or smaller.",
        )

    try:
        return await asyncio.wait_for(
            process_vision_request(
                content=content,
                filename=file.filename or "upload",
                mime_type=file.content_type or "application/octet-stream",
                prompt=prompt,
                operation=operation,
                settings=settings,
            ),
            timeout=float(settings.vision_timeout_seconds) + 15.0,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="Image/file analysis timed out. Retry with a smaller or clearer file.",
        ) from exc
    except Exception as exc:
        detail = str(exc)[:1600]
        raise HTTPException(
            status_code=503,
            detail=detail or "Image/file analysis failed.",
        ) from exc


@app.get("/api/image/status")
async def image_status() -> dict:
    return {
        "ok": True,
        "cloudflare_configured": bool(
            settings.cloudflare_account_id
            and settings.cloudflare_workers_ai
        ),
        "huggingface_configured": bool(
            settings.hugging_face_inference_api
        ),
        "deepai_configured": bool(settings.deepai_api),
        "image_retry_attempts": settings.image_retry_attempts,
        "image_timeout_seconds": settings.image_timeout_seconds,
        "total_image_timeout_seconds": settings.total_image_timeout_seconds,
    }


@app.post("/api/image")
async def generate_image(
    request: ImageRequest,
    _current_user: AuthUser = Depends(get_current_user),
) -> dict:
    try:
        return await asyncio.wait_for(
            route_image(request.provider, request.prompt, settings),
            timeout=float(settings.total_image_timeout_seconds),
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="Image generation timed out after automatic provider retries.",
        ) from exc
    except Exception as exc:
        detail = str(exc)[:1200]
        raise HTTPException(
            status_code=503,
            detail=detail or "All image providers failed.",
        ) from exc


@app.post("/api/ocr")
async def ocr(
    file: UploadFile = File(...),
    _current_user: AuthUser = Depends(get_current_user),
) -> dict:
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File must be under 10 MB")

    try:
        return await extract_text(file, settings)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="OCR service is temporarily unavailable.",
        ) from exc
