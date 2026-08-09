from __future__ import annotations

from typing import Any

from fastapi import Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

import app.main_v9_phase1 as phase1
from app.auth import AuthUser, get_current_user
from app.services.coding_agent_v9 import generate_coding_plan
from app.services.project_kb_v9 import (
    apply_project_changes,
    build_project_codebase_map,
    delete_project_file,
    list_project_files,
    upsert_project_files,
)

app = phase1.app
settings = phase1.settings


class CodePlanRequest(BaseModel):
    instruction: str = Field(..., min_length=3, max_length=12000)
    target_paths: list[str] = Field(default_factory=list, max_length=30)


class CodeApplyRequest(BaseModel):
    changes: list[dict[str, Any]] = Field(..., min_length=1, max_length=12)


class DebugRequest(BaseModel):
    instruction: str = Field(default="Fix this bug safely.", min_length=3, max_length=12000)
    error_log: str = Field(..., min_length=1, max_length=20000)
    target_paths: list[str] = Field(default_factory=list, max_length=30)


@app.get("/api/projects/{project_id}/kb/files")
async def api_project_kb_files(
    project_id: str,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    rows = await list_project_files(
        settings,
        user_id=current_user.id,
        project_id=project_id,
        include_content=False,
        limit=500,
    )
    return {"files": rows}


@app.post("/api/projects/{project_id}/kb/files")
async def api_upload_project_kb_files(
    project_id: str,
    files: list[UploadFile] = File(default=[]),
    paths: list[str] = Form(default=[]),
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not files or len(files) > 30:
        raise HTTPException(status_code=400, detail="Upload between 1 and 30 project files.")
    uploads: list[dict[str, Any]] = []
    total = 0
    for index, upload in enumerate(files):
        content = await upload.read()
        total += len(content)
        uploads.append({
            "filename": upload.filename or f"file-{index + 1}.txt",
            "path": paths[index] if index < len(paths) and paths[index].strip() else (upload.filename or f"file-{index + 1}.txt"),
            "mime_type": upload.content_type or "text/plain",
            "content": content,
        })
    if total > 30 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Combined Project KB upload must be 30 MB or smaller.")
    try:
        rows = await upsert_project_files(
            settings,
            user_id=current_user.id,
            project_id=project_id,
            uploads=uploads,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "files": rows}


@app.delete("/api/projects/{project_id}/kb/files")
async def api_delete_project_kb_file(
    project_id: str,
    path: str = Query(..., min_length=1, max_length=260),
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        ok = await delete_project_file(
            settings,
            user_id=current_user.id,
            project_id=project_id,
            path=path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": ok}


@app.get("/api/projects/{project_id}/kb/map")
async def api_project_kb_map(
    project_id: str,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "map": await build_project_codebase_map(
                settings,
                user_id=current_user.id,
                project_id=project_id,
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/code/patch")
async def api_code_patch(
    project_id: str,
    payload: CodePlanRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await generate_coding_plan(
            settings,
            user_id=current_user.id,
            project_id=project_id,
            instruction=payload.instruction,
            target_paths=payload.target_paths,
            mode="patch",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/code/apply")
async def api_code_apply(
    project_id: str,
    payload: CodeApplyRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await apply_project_changes(
            settings,
            user_id=current_user.id,
            project_id=project_id,
            changes=payload.changes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/tests/generate")
async def api_generate_tests(
    project_id: str,
    payload: CodePlanRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await generate_coding_plan(
            settings,
            user_id=current_user.id,
            project_id=project_id,
            instruction=payload.instruction,
            target_paths=payload.target_paths,
            mode="tests",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/debug")
async def api_auto_debug(
    project_id: str,
    payload: DebugRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await generate_coding_plan(
            settings,
            user_id=current_user.id,
            project_id=project_id,
            instruction=payload.instruction,
            target_paths=payload.target_paths,
            mode="debug",
            debug_log=payload.error_log,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/health/v9-phase2")
async def health_v9_phase2() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v9-phase2-part1",
        "project_kb_v2": True,
        "cross_file_codebase_understanding": True,
        "code_patch_mode": True,
        "multi_file_changes": True,
        "browser_code_sandbox": True,
        "test_generation": True,
        "automatic_debug_mode": True,
        "server_side_arbitrary_code_execution": False,
        "note": "Web code executes only inside a sandboxed browser iframe; arbitrary server-side code execution is intentionally disabled.",
    }
