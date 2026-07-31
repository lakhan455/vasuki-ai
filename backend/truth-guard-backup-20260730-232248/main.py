from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.schemas import ChatRequest, ChatResponse, ImageRequest, ResearchRequest
from app.services.chat import route_chat
from app.services.image import route_image
from app.services.ocr import extract_text
from app.services.research import needs_live_web, search_web

settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict:
    return {"name": settings.app_name, "status": "online", "docs": "/docs", "version": "1.1.0"}


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "environment": settings.app_env}


@app.post("/api/research")
async def research(request: ResearchRequest) -> dict:
    current_date = datetime.now(timezone.utc).date().isoformat()
    results, provider = await search_web(
        request.query,
        settings,
        request.max_results,
        require_current=needs_live_web(request.query),
        as_of=current_date,
    )
    return {"results": results, "provider": provider, "as_of": current_date}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    messages = [item.model_dump() for item in request.messages]
    total_chars = sum(len(item["content"]) for item in messages)
    if total_chars > settings.max_prompt_chars:
        raise HTTPException(status_code=413, detail="Conversation is too long")

    query = next((item["content"] for item in reversed(messages) if item["role"] == "user"), "")
    current_date = datetime.now(timezone.utc).date().isoformat()

    # Live verification is mandatory for time-sensitive questions, regardless
    # of the frontend checkbox. This prevents stale office-holder answers.
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
            reason = search_provider or "No live source returned"
            raise HTTPException(
                status_code=503,
                detail=(
                    "This question requires current web verification, but no reliable live source was available. "
                    f"The AI did not answer from old model memory. Search status: {reason}"
                ),
            )

        if sources:
            context_parts: list[str] = []
            for index, source in enumerate(sources, 1):
                published = source.get("published_date") or "not provided"
                context_parts.append(
                    f"[{index}] {source['title']}\n"
                    f"URL: {source['url']}\n"
                    f"Published/updated date: {published}\n"
                    f"Extracted content:\n{source['content']}"
                )
            web_context = "\n\n".join(context_parts)

    try:
        answer, provider = await route_chat(
            request.provider,
            messages,
            settings,
            web_context,
            require_current=require_current,
            as_of=current_date,
        )
        return ChatResponse(answer=answer, provider=provider, sources=sources)
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
