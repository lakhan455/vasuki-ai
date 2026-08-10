from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

import app.main_v9_phase5 as phase5
from app.auth import AuthUser, get_current_user
from app.services.analytics_v8 import jwt_subject
from app.services.backup_v9 import create_backup, list_backups, restore_backup
from app.services.plans_v2 import get_plan_status
from app.services.security_v9_phase6 import (
    audit_event, error_dashboard, error_event, list_audit_logs, list_evals,
    record_eval, record_secret_rotation, release_health, resolve_error, security_audit,
)

app = phase5.app
settings = phase5.settings

class SecretRotationRequest(BaseModel):
    secret_name: str = Field(..., min_length=3, max_length=120)
    previous_fingerprint: str = Field(..., min_length=4, max_length=64)
    note: str = Field(default="", max_length=1000)

class BackupCreateRequest(BaseModel):
    note: str = Field(default="", max_length=1000)

class BackupRestoreRequest(BaseModel):
    apply: bool = False
    confirmation: str = Field(default="", max_length=100)

class EvalRunRequest(BaseModel):
    version: str = Field(default="v9-phase6", max_length=80)
    questions: int = Field(default=0, ge=0, le=100000)
    overall: float = Field(default=0, ge=0, le=100)
    average_latency_ms: float = Field(default=0, ge=0)
    scores: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

async def _require_owner(current_user: AuthUser) -> None:
    status = await get_plan_status(current_user, settings)
    if not status.is_owner:
        raise HTTPException(status_code=403, detail="Owner access required.")

@app.middleware("http")
async def phase6_security_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    started = time.perf_counter()
    user_id = jwt_subject(request.headers.get("authorization"))
    ip_value = request.headers.get("x-forwarded-for") or (request.client.host if request.client else None)
    user_agent = request.headers.get("user-agent")
    try:
        response = await call_next(request)
    except Exception as exc:
        asyncio.create_task(error_event(settings, request_id=request_id, event_type="unhandled_exception", message=f"{type(exc).__name__}: {str(exc)[:2500]}", severity="critical", metadata={"path": request.url.path, "method": request.method}))
        asyncio.create_task(audit_event(settings, actor_user_id=user_id, action=f"{request.method} {request.url.path}", outcome="exception", request_id=request_id, ip_value=ip_value, user_agent=user_agent, metadata={"latency_ms": round((time.perf_counter() - started) * 1000, 1)}))
        raise
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), usb=(), serial=()"
    response.headers["X-Frame-Options"] = "DENY"
    latency = round((time.perf_counter() - started) * 1000, 1)
    if response.status_code >= 500:
        asyncio.create_task(error_event(settings, request_id=request_id, event_type="http_5xx", message=f"HTTP {response.status_code} on {request.method} {request.url.path}", severity="error", metadata={"path": request.url.path, "method": request.method, "status": response.status_code, "latency_ms": latency}))
    if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        asyncio.create_task(audit_event(settings, actor_user_id=user_id, action=f"{request.method.upper()} {request.url.path}", outcome="success" if response.status_code < 400 else "rejected", request_id=request_id, ip_value=ip_value, user_agent=user_agent, metadata={"status": response.status_code, "latency_ms": latency}))
    return response

@app.get("/api/owner/security-center/v9")
async def owner_security_center(days: int = Query(7, ge=1, le=90), current_user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    await _require_owner(current_user)
    audits, errors, backups, evals, release = await asyncio.gather(
        list_audit_logs(settings, days=days, limit=180), error_dashboard(settings, days=days),
        list_backups(settings, limit=30), list_evals(settings, limit=20), release_health(settings),
    )
    return {"ok": True, "security": security_audit(settings), "audit_logs": audits, "errors": errors, "backups": backups, "evals": evals, "release_health": release}

@app.get("/api/owner/audit/v9")
async def owner_audit_logs(days: int = Query(7, ge=1, le=90), limit: int = Query(200, ge=1, le=500), current_user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    await _require_owner(current_user); return {"logs": await list_audit_logs(settings, days=days, limit=limit)}

@app.post("/api/owner/secrets/v9/rotation")
async def owner_record_secret_rotation(payload: SecretRotationRequest, current_user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    await _require_owner(current_user)
    try:
        row = await record_secret_rotation(settings, owner_user_id=current_user.id, secret_name=payload.secret_name, previous_fingerprint=payload.previous_fingerprint, note=payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "rotation": row}

@app.get("/api/owner/backups/v9")
async def owner_backups(current_user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    await _require_owner(current_user); return {"backups": await list_backups(settings)}

@app.post("/api/owner/backups/v9")
async def owner_create_backup(payload: BackupCreateRequest, current_user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    await _require_owner(current_user)
    try:
        backup = await create_backup(settings, owner_user_id=current_user.id, note=payload.note)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "backup": backup}

@app.post("/api/owner/backups/v9/{backup_id}/restore")
async def owner_restore_backup(backup_id: str, payload: BackupRestoreRequest, current_user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    await _require_owner(current_user)
    try:
        return await restore_backup(settings, backup_id=backup_id, apply=payload.apply, confirmation=payload.confirmation)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get("/api/owner/errors/v9")
async def owner_errors(days: int = Query(7, ge=1, le=90), current_user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    await _require_owner(current_user); return await error_dashboard(settings, days=days)

@app.patch("/api/owner/errors/v9/{error_id}/resolve")
async def owner_resolve_error(error_id: int, current_user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    await _require_owner(current_user); return {"ok": await resolve_error(settings, error_id=error_id, owner_user_id=current_user.id)}

@app.get("/api/owner/release-health/v9")
async def owner_release_health(current_user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    await _require_owner(current_user); return {"ok": True, **await release_health(settings)}

@app.get("/api/owner/evals/v9")
async def owner_evals(limit: int = Query(20, ge=1, le=100), current_user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    await _require_owner(current_user); return {"evals": await list_evals(settings, limit=limit)}

@app.post("/api/owner/evals/v9")
async def owner_record_eval(payload: EvalRunRequest, current_user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    await _require_owner(current_user); return {"ok": True, "eval": await record_eval(settings, owner_user_id=current_user.id, payload=payload.model_dump())}

@app.get("/health/v9-phase6")
async def health_v9_phase6() -> dict[str, Any]:
    return {
        "ok": True, "version": "v9-phase6", "security_audit_v2": True, "audit_logs": True,
        "secret_rotation_workflow": True, "application_backup_restore": True,
        "error_tracking_dashboard": True, "release_health_checks": True,
        "ci_security_scan": True, "vasuki_eval_score": True, "security_headers": True,
        "backup_note": "Backup/restore is application-level logical protection; it does not replace Supabase native database/storage backups and does not back up Auth identities or storage object bytes.",
        "rotation_note": "Secret values are rotated in Render/provider dashboards; Vasuki records fingerprints and verifies that a running secret changed without exposing the value.",
    }
