from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import AuthUser, get_current_user
from app.services.plans_v2 import get_plan_status
from app.v49.live_knowledge import live_knowledge_status, refresh_now


class RefreshRequest(BaseModel):
    topic_id: str | None = Field(default=None, max_length=120)
    query: str | None = Field(default=None, max_length=700)


async def _require_owner(settings: Any, user: AuthUser) -> None:
    status = await get_plan_status(user, settings)
    if not status.is_owner:
        raise HTTPException(status_code=403, detail="Owner access required.")


def build_router(settings: Any) -> APIRouter:
    router = APIRouter(tags=["v49-live-knowledge"])

    @router.get("/health/v49")
    async def health_v49():
        status = live_knowledge_status(settings)
        return {
            "ok": status["ok"],
            "version": status["version"],
            "name": status["name"],
            "enabled": status["enabled"],
            "search_ready": status["search_ready"],
            "storage_ready": status["storage_ready"],
            "last_success_at": status["runtime"]["last_success_at"],
            "pending_adaptive_queries": status["pending_adaptive_queries"],
            "hosting_note": status["hosting_note"],
        }

    @router.get("/api/owner/v49/live-knowledge")
    async def owner_live_knowledge(user: AuthUser = Depends(get_current_user)):
        await _require_owner(settings, user)
        return live_knowledge_status(settings)

    @router.post("/api/owner/v49/live-knowledge/refresh")
    async def owner_live_knowledge_refresh(
        payload: RefreshRequest,
        user: AuthUser = Depends(get_current_user),
    ):
        await _require_owner(settings, user)
        try:
            return await refresh_now(
                settings,
                topic_id=payload.topic_id,
                query=payload.query,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return router
