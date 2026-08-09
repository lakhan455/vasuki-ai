from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import Depends, File, Form, HTTPException, Request, UploadFile

import app.main_v8 as v8
from app.auth import AuthUser, get_current_user
from app.routes.smart_files import settings as smart_settings
from app.services.analytics_v8 import analytics_snapshot, jwt_subject, log_usage
from app.services.artifacts_v8 import (
    cleanup_expired,
    delete_artifact,
    list_artifacts,
    save_artifact,
)
from app.services.cache_v7 import RESPONSE_CACHE, WEB_CACHE
from app.services.file_artifacts import process_smart_file_request
from app.services.image_health_v8 import snapshot as image_health_snapshot
from app.services.image_v8 import route_image_v8
from app.services.plans_v2 import get_plan_status
from app.services.telemetry_v7 import snapshot as chat_health_snapshot

app = v8.app
settings = v8.settings


def _feature_for_path(path: str) -> str | None:
    if path.startswith("/api/chat"):
        return "chat"
    if path.startswith("/api/research"):
        return "research"
    if path.startswith("/api/vision"):
        return "vision"
    if path.startswith("/api/image"):
        return "image"
    if path.startswith("/api/smart-files"):
        return "files"
    if path.startswith("/api/documents"):
        return "rag"
    return None


@app.middleware("http")
async def v8_usage_middleware(request: Request, call_next):
    feature = _feature_for_path(request.url.path)
    if not feature:
        return await call_next(request)
    started = time.perf_counter()
    response = await call_next(request)
    latency = round((time.perf_counter() - started) * 1000, 1)
    user_id = jwt_subject(request.headers.get("authorization")) if response.status_code < 400 else None
    asyncio.create_task(
        log_usage(
            settings,
            feature=feature,
            user_id=user_id,
            status=str(response.status_code),
            latency_ms=latency,
            metadata={"path": request.url.path},
        )
    )
    return response


@app.post("/api/image/v2")
async def generate_image_v2(
    payload: v8.legacy.ImageRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    started = time.perf_counter()
    status = await get_plan_status(current_user, settings)
    try:
        result = await asyncio.wait_for(
            route_image_v8(payload.provider, payload.prompt, settings, max_attempts=2),
            timeout=float(settings.total_image_timeout_seconds),
        )
        image_url = str(result.get("url") or "")
        artifact = await save_artifact(
            settings,
            user_id=current_user.id,
            name=f"Vasuki {result.get('image_type') or 'image'}",
            artifact_type="image",
            mime_type="image/png" if image_url.startswith("data:image/png") else "image/jpeg",
            data_url=image_url if image_url.startswith("data:") else None,
            external_url=image_url if image_url.startswith("http") else None,
            prompt=payload.prompt,
            provider=str(result.get("provider") or ""),
            retention_days=30 if status.plan in {"owner", "pro"} else 15,
        )
        await log_usage(
            settings,
            feature="image_generation",
            user_id=current_user.id,
            provider=str(result.get("provider") or ""),
            status="ok",
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            metadata={
                "image_type": result.get("image_type"),
                "plan": status.plan,
                "artifact_id": (artifact or {}).get("id"),
            },
        )
        return {**result, "artifact": artifact, "plan": status.plan}
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Image generation timed out.") from exc
    except Exception as exc:
        await log_usage(
            settings,
            feature="image_generation",
            user_id=current_user.id,
            status="error",
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            metadata={"error": str(exc)[:500]},
        )
        raise HTTPException(status_code=503, detail=str(exc)[:1200]) from exc


@app.get("/api/images/history")
async def image_history(
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    files = await list_artifacts(settings, current_user.id, limit=100)
    return {"images": [item for item in files if item.get("artifact_type") == "image"]}


@app.post("/api/smart-files/v2")
async def smart_files_v2(
    prompt: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    clean_prompt = prompt.strip()
    if not clean_prompt:
        raise HTTPException(status_code=400, detail="Write an instruction or question first.")
    if len(clean_prompt) > 12000:
        raise HTTPException(status_code=400, detail="Instruction must be 12,000 characters or shorter.")
    if len(files) > 8:
        raise HTTPException(status_code=400, detail="Upload up to 8 files at a time.")

    uploads: list[dict[str, object]] = []
    total = 0
    for upload in files:
        content = await upload.read()
        total += len(content)
        uploads.append({
            "filename": upload.filename or "document",
            "mime_type": upload.content_type or "application/octet-stream",
            "content": content,
        })
    if total > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Combined upload size must be 50 MB or smaller.")

    result = await process_smart_file_request(
        uploads=uploads,
        prompt=clean_prompt,
        settings=smart_settings,
    )
    stored = []
    for item in result.get("files") or []:
        saved = await save_artifact(
            settings,
            user_id=current_user.id,
            name=str(item.get("name") or "Vasuki AI file"),
            artifact_type="file",
            mime_type=str(item.get("mime_type") or "application/octet-stream"),
            data_url=str(item.get("data_url") or ""),
            prompt=clean_prompt,
            provider=str(result.get("provider") or ""),
            retention_days=30,
        )
        if saved:
            stored.append(saved)
    await log_usage(
        settings,
        feature="smart_files",
        user_id=current_user.id,
        provider=str(result.get("provider") or ""),
        status="ok",
        metadata={"uploaded_files": len(files), "generated_artifacts": len(stored)},
    )
    asyncio.create_task(cleanup_expired(settings))
    return {**result, "stored_files": stored}


@app.get("/api/files")
async def my_files(
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    asyncio.create_task(cleanup_expired(settings))
    return {"files": await list_artifacts(settings, current_user.id, limit=200)}


@app.delete("/api/files/{artifact_id}")
async def remove_file(
    artifact_id: str,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {"ok": await delete_artifact(settings, current_user.id, artifact_id)}


@app.get("/api/owner/analytics/v2")
async def owner_analytics(
    days: int = 7,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    plan = await get_plan_status(current_user, settings)
    if not plan.is_owner:
        raise HTTPException(status_code=403, detail="Owner access required.")
    persistent = await analytics_snapshot(settings, days=days)
    return {
        "ok": True,
        "persistent": persistent,
        "chat_provider_health": chat_health_snapshot(),
        "image_provider_health": image_health_snapshot(),
        "cache": {
            "responses": RESPONSE_CACHE.snapshot(),
            "web": WEB_CACHE.snapshot(),
        },
    }


@app.get("/health/v8-phase2")
async def health_v8_phase2() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v8-phase2-core",
        "base": "v8-foundation",
        "owner_analytics": True,
        "smart_image_router": True,
        "image_prompt_enhancer": True,
        "image_history": True,
        "artifact_manager": True,
        "artifact_cleanup": True,
        "usage_tracking": True,
    }
