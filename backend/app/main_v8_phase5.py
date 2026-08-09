from __future__ import annotations

from typing import Any

from fastapi import Depends
from pydantic import BaseModel, Field

import app.main_v8_phase4 as phase4
from app.auth import AuthUser, get_current_user
from app.services.project_memory_auto_v8 import auto_capture_project_memories

app = phase4.app
settings = phase4.settings


class AutoProjectMemoryRequest(BaseModel):
    messages: list[dict[str, Any]] = Field(default_factory=list, max_length=30)


@app.post("/api/projects/{project_id}/memories/auto-extract")
async def api_auto_extract_project_memories(
    project_id: str,
    payload: AutoProjectMemoryRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return await auto_capture_project_memories(
        settings,
        user_id=current_user.id,
        project_id=project_id,
        messages=payload.messages,
    )


@app.get("/health/v8-phase5")
async def health_v8_phase5() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v8-phase5-start",
        "smart_regenerate_v2": True,
        "cache_bypass_regenerate": True,
        "provider_exclusion_regenerate": True,
        "automatic_project_memory": True,
        "deep_research_v2": True,
        "live_code_preview": True,
        "project_context_normal_chat_fix": True,
        "sql_migration_required": False,
    }
