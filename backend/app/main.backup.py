from __future__ import annotations
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.schemas import ChatRequest, ChatResponse, ResearchRequest, ImageRequest
from app.services.chat import route_chat
from app.services.research import search_web
from app.services.image import route_image
from app.services.ocr import extract_text

settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict:
    return {"name": settings.app_name, "status": "online", "docs": "/docs"}


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "environment": settings.app_env}


@app.post("/api/research")
async def research(request: ResearchRequest) -> dict:
    results, provider = await search_web(request.query, settings, request.max_results)
    return {"results": results, "provider": provider}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    messages = [item.model_dump() for item in request.messages]
    total_chars = sum(len(item["content"]) for item in messages)
    if total_chars > settings.max_prompt_chars:
        raise HTTPException(status_code=413, detail="Conversation is too long")

    sources: list[dict] = []
    web_context = ""
    if request.use_web:
        query = next((item["content"] for item in reversed(messages) if item["role"] == "user"), "")
        sources, _ = await search_web(query, settings, 5)
        if sources:
            web_context = "\n\n".join(
                f"[{index}] {source['title']}\nURL: {source['url']}\n{source['content']}"
                for index, source in enumerate(sources, 1)
            )

    try:
        answer, provider = await route_chat(request.provider, messages, settings, web_context)
        return ChatResponse(answer=answer, provider=provider, sources=sources)
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
