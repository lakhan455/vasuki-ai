from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field

import app.main_v8_phase3_part2 as phase3_part2
from app.auth import AuthUser, get_current_user
from app.services.chat_history_v8 import list_recent_branches_all, search_chat_history
from app.services.project_memory_v8 import (
    add_project_memory,
    delete_project_memory,
    list_project_memories,
)

app = phase3_part2.app
settings = phase3_part2.settings


class ProjectMemoryCreateRequest(BaseModel):
    memory_text: str = Field(..., min_length=3, max_length=1200)


@app.get("/api/projects/{project_id}/memories")
async def api_project_memories(
    project_id: str,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "memories": await list_project_memories(
            settings,
            user_id=current_user.id,
            project_id=project_id,
            limit=150,
        )
    }


@app.post("/api/projects/{project_id}/memories")
async def api_add_project_memory(
    project_id: str,
    payload: ProjectMemoryCreateRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        item = await add_project_memory(
            settings,
            user_id=current_user.id,
            project_id=project_id,
            memory_text=payload.memory_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"memory": item}


@app.delete("/api/projects/{project_id}/memories/{memory_id}")
async def api_delete_project_memory(
    project_id: str,
    memory_id: str,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "ok": await delete_project_memory(
            settings,
            user_id=current_user.id,
            project_id=project_id,
            memory_id=memory_id,
        )
    }


@app.get("/api/chat/search")
async def api_chat_search(
    q: str = Query(..., min_length=2, max_length=300),
    limit: int = Query(default=24, ge=1, le=50),
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "results": await search_chat_history(
            settings,
            user_id=current_user.id,
            query=q,
            limit=limit,
        )
    }


@app.get("/api/chat/branches/recent")
async def api_recent_branches(
    limit: int = Query(default=100, ge=1, le=200),
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "branches": await list_recent_branches_all(
            settings,
            user_id=current_user.id,
            limit=limit,
        )
    }


@app.get("/health/v8-phase4")
async def health_v8_phase4() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v8-phase4-start",
        "project_specific_memory": True,
        "project_context_in_chat": True,
        "project_chat_association": True,
        "chat_history_search": True,
        "branch_explorer": True,
        "semantic_project_memory": True,
        "lexical_fallback": True,
    }
