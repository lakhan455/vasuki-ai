from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

import app.main_v8_phase2 as phase2
from app.auth import AuthUser, get_current_user
from app.services.branching_v8 import create_branch, list_branches
from app.services.feedback_v8 import save_feedback
from app.services.projects_v8 import create_project, delete_project, list_projects, update_project
from app.services.plans_v2 import get_plan_status

app = phase2.app
settings = phase2.settings


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    instructions: str | None = Field(default=None, max_length=12000)
    color: str | None = Field(default='#8b5cf6', max_length=20)


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    instructions: str | None = Field(default=None, max_length=12000)
    color: str | None = Field(default=None, max_length=20)
    archived: bool | None = None


class FeedbackRequest(BaseModel):
    rating: str = Field(..., pattern='^(up|down)$')
    category: str = Field(default='other', max_length=50)
    message_id: str | None = Field(default=None, max_length=120)
    comment: str | None = Field(default=None, max_length=3000)
    metadata: dict[str, Any] | None = None


class BranchCreateRequest(BaseModel):
    conversation_id: str = Field(..., min_length=1, max_length=120)
    source_message_id: str | None = Field(default=None, max_length=120)
    original_prompt: str = Field(..., min_length=1, max_length=12000)
    edited_prompt: str = Field(..., min_length=1, max_length=12000)
    note: str | None = Field(default=None, max_length=2000)


@app.get('/api/projects')
async def api_list_projects(current_user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    return {'projects': await list_projects(settings, current_user.id)}


@app.post('/api/projects')
async def api_create_project(
    payload: ProjectCreateRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    project = await create_project(
        settings,
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        instructions=payload.instructions,
        color=payload.color,
    )
    return {'project': project}


@app.patch('/api/projects/{project_id}')
async def api_update_project(
    project_id: str,
    payload: ProjectUpdateRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    project = await update_project(settings, user_id=current_user.id, project_id=project_id, patch=payload.model_dump(exclude_none=True))
    if not project:
        raise HTTPException(status_code=404, detail='Project not found or no changes provided.')
    return {'project': project}


@app.delete('/api/projects/{project_id}')
async def api_delete_project(
    project_id: str,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {'ok': await delete_project(settings, user_id=current_user.id, project_id=project_id)}


@app.post('/api/feedback')
async def api_feedback(
    payload: FeedbackRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    item = await save_feedback(
        settings,
        user_id=current_user.id,
        rating=payload.rating,
        category=payload.category,
        message_id=payload.message_id,
        comment=payload.comment,
        metadata=payload.metadata,
    )
    return {'feedback': item}


@app.post('/api/chat/branch')
async def api_create_branch(
    payload: BranchCreateRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    item = await create_branch(
        settings,
        user_id=current_user.id,
        conversation_id=payload.conversation_id,
        source_message_id=payload.source_message_id,
        original_prompt=payload.original_prompt,
        edited_prompt=payload.edited_prompt,
        note=payload.note,
    )
    return {'branch': item}


@app.get('/api/chat/branches')
async def api_list_branches(
    conversation_id: str,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {'branches': await list_branches(settings, user_id=current_user.id, conversation_id=conversation_id)}


@app.get('/api/owner/phase3/bootstrap')
async def owner_phase3_bootstrap(current_user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    plan = await get_plan_status(current_user, settings)
    if not plan.is_owner:
        raise HTTPException(status_code=403, detail='Owner access required.')
    base = await phase2.owner_analytics(days=7, current_user=current_user)
    return {
        'ok': True,
        'analytics': base,
        'phase': 'v8-phase3-start',
    }


@app.get('/health/v8-phase3')
async def health_v8_phase3() -> dict[str, Any]:
    return {
        'ok': True,
        'version': 'v8-phase3-start',
        'projects': True,
        'feedback': True,
        'branching': True,
        'files_ui': True,
        'images_ui': True,
        'owner_ui': True,
    }
