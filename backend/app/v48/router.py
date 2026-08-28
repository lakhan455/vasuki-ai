from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.auth import AuthUser, get_current_user
from app.v11.scheduler import create_task, runtime_note
from app.v48.data_analysis import analyze_tabular_bytes, spreadsheet_text
from app.v48.file_library import delete_file, list_files, signed_download_url, upload_file
from app.v48.tasks import delete_task, list_tasks, update_task
from app.v48.tool_hub import tool_hub_health


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=12000)
    run_at: str | None = None
    cron: str | None = None


class TaskUpdateRequest(BaseModel):
    status: str | None = None
    title: str | None = Field(default=None, max_length=200)
    prompt: str | None = Field(default=None, max_length=12000)
    run_at: str | None = None
    cron: str | None = None


def build_router(settings: Any) -> APIRouter:
    router = APIRouter(tags=["v48-tools"])

    @router.get("/health/v48")
    async def health_v48():
        return tool_hub_health(settings)

    @router.get("/api/v48/tools")
    async def tools_v48(_user: AuthUser = Depends(get_current_user)):
        return tool_hub_health(settings)

    @router.post("/api/v48/data/analyze")
    async def data_analyze(
        file: UploadFile = File(...),
        _user: AuthUser = Depends(get_current_user),
    ):
        data = await file.read()
        try:
            report = analyze_tabular_bytes(file.filename or "data.csv", data)
        except (ValueError, RuntimeError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return report

    @router.post("/api/v48/data/context")
    async def data_context(
        file: UploadFile = File(...),
        _user: AuthUser = Depends(get_current_user),
    ):
        data = await file.read()
        try:
            return {"ok": True, "context": spreadsheet_text(file.filename or "data.csv", data)}
        except (ValueError, RuntimeError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/api/v48/library/files")
    async def library_upload(
        file: UploadFile = File(...),
        user: AuthUser = Depends(get_current_user),
    ):
        data = await file.read()
        try:
            item = await upload_file(
                settings,
                user_id=user.id,
                filename=file.filename or "file",
                content_type=file.content_type or "application/octet-stream",
                data=data,
            )
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"ok": True, "file": item}

    @router.get("/api/v48/library/files")
    async def library_list(user: AuthUser = Depends(get_current_user)):
        try:
            items = await list_files(settings, user_id=user.id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"ok": True, "files": items}

    @router.post("/api/v48/library/download")
    async def library_download(
        path: str = Form(...),
        user: AuthUser = Depends(get_current_user),
    ):
        try:
            url = await signed_download_url(settings, user_id=user.id, path=path)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"ok": True, "url": url, "expires_seconds": 900}

    @router.delete("/api/v48/library/files")
    async def library_delete(
        path: str,
        user: AuthUser = Depends(get_current_user),
    ):
        try:
            await delete_file(settings, user_id=user.id, path=path)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"ok": True}

    @router.post("/api/v48/tasks")
    async def tasks_create(payload: TaskCreateRequest, user: AuthUser = Depends(get_current_user)):
        if not payload.run_at and not payload.cron:
            raise HTTPException(status_code=422, detail="run_at or cron is required.")
        try:
            task = await create_task(
                settings,
                user_id=user.id,
                title=payload.title,
                prompt=payload.prompt,
                run_at=payload.run_at,
                cron=payload.cron,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"ok": True, "task": task, "runtime_note": runtime_note()}

    @router.get("/api/v48/tasks")
    async def tasks_list(user: AuthUser = Depends(get_current_user)):
        return {"ok": True, "tasks": await list_tasks(settings, user_id=user.id), "runtime_note": runtime_note()}

    @router.patch("/api/v48/tasks/{task_id}")
    async def tasks_update(task_id: str, payload: TaskUpdateRequest, user: AuthUser = Depends(get_current_user)):
        try:
            task = await update_task(
                settings,
                user_id=user.id,
                task_id=task_id,
                status=payload.status,
                title=payload.title,
                prompt=payload.prompt,
                run_at=payload.run_at,
                cron=payload.cron,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found or persistent scheduler storage is unavailable.")
        return {"ok": True, "task": task}

    @router.delete("/api/v48/tasks/{task_id}")
    async def tasks_delete(task_id: str, user: AuthUser = Depends(get_current_user)):
        ok = await delete_task(settings, user_id=user.id, task_id=task_id)
        if not ok:
            raise HTTPException(status_code=503, detail="Persistent scheduler storage is unavailable.")
        return {"ok": True}

    return router
