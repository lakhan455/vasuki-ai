from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import AuthUser, get_current_user
from app.config import get_settings
from app.services.plans_v2 import get_plan_status
from app.v11.quality import run_eval
from app.v12.citations import verify_citations_v12
from app.v12.coding import apply_exact_patches, test_fix_retest
from app.v12.dashboard import reliability_snapshot_v12
from app.v12.memory import resolve_conflicts_v12
from app.v12.provider import provider_snapshot_v12
from app.v12.sandbox import run_sandbox, sandbox_status


router = APIRouter()
settings = get_settings()


async def require_owner(user: AuthUser) -> None:
    status = await get_plan_status(user, settings)

    if not status.is_owner:
        raise HTTPException(
            status_code=403,
            detail="Owner access required.",
        )


class CitationRequestV12(BaseModel):
    answer: str = Field(max_length=120000)
    sources: list[dict[str, Any]] = Field(default_factory=list)


class MemoryResolveRequestV12(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)


class SandboxRequestV12(BaseModel):
    files: dict[str, str]
    runtime: str = "python"
    command: str = "python -m pytest -q"
    timeout_seconds: int = Field(default=25, ge=1, le=60)


class CodeTestFixRequestV12(BaseModel):
    instruction: str = Field(min_length=2, max_length=20000)
    files: dict[str, str]
    runtime: str = "python"
    test_command: str = "python -m pytest -q"
    max_attempts: int = Field(default=3, ge=1, le=3)
    timeout_seconds: int = Field(default=25, ge=1, le=60)


class ExactPatchRequestV12(BaseModel):
    files: dict[str, str]
    patches: list[dict[str, Any]]


@router.get("/api/v12/status")
async def v12_status(
    _user: AuthUser = Depends(get_current_user),
):
    return reliability_snapshot_v12(settings)


@router.get("/api/owner/v12/reliability")
async def owner_v12_reliability(
    user: AuthUser = Depends(get_current_user),
):
    await require_owner(user)
    return reliability_snapshot_v12(settings)


@router.get("/api/owner/v12/providers")
async def owner_v12_providers(
    user: AuthUser = Depends(get_current_user),
):
    await require_owner(user)

    return {
        "ok": True,
        "providers": provider_snapshot_v12(settings),
    }


@router.post("/api/v12/citations/verify")
async def citations_v12(
    payload: CitationRequestV12,
    _user: AuthUser = Depends(get_current_user),
):
    return {
        "ok": True,
        "verification": verify_citations_v12(
            payload.answer,
            payload.sources,
        ),
    }


@router.post("/api/v12/memory/resolve")
async def memory_resolve_v12(
    payload: MemoryResolveRequestV12,
    _user: AuthUser = Depends(get_current_user),
):
    return {
        "ok": True,
        "memory": resolve_conflicts_v12(payload.rows),
    }


@router.get("/api/owner/v12/sandbox")
async def sandbox_health_v12(
    user: AuthUser = Depends(get_current_user),
):
    await require_owner(user)

    return {
        "ok": True,
        "sandbox": sandbox_status(),
    }


@router.post("/api/owner/v12/sandbox/run")
async def sandbox_run_v12(
    payload: SandboxRequestV12,
    user: AuthUser = Depends(get_current_user),
):
    await require_owner(user)

    if len(payload.files) > 100:
        raise HTTPException(
            status_code=413,
            detail="Too many sandbox files.",
        )

    return await run_sandbox(
        payload.files,
        runtime=payload.runtime,
        command=payload.command,
        timeout_seconds=payload.timeout_seconds,
    )


@router.post("/api/owner/v12/code/test-fix")
async def code_test_fix_v12(
    payload: CodeTestFixRequestV12,
    user: AuthUser = Depends(get_current_user),
):
    await require_owner(user)

    total = sum(len(value) for value in payload.files.values())

    if len(payload.files) > 100 or total > 500000:
        raise HTTPException(
            status_code=413,
            detail="Project snapshot is too large.",
        )

    return await test_fix_retest(
        instruction=payload.instruction,
        files=payload.files,
        runtime=payload.runtime,
        test_command=payload.test_command,
        settings=settings,
        max_attempts=payload.max_attempts,
        timeout_seconds=payload.timeout_seconds,
    )


@router.post("/api/v12/code/apply-patches")
async def code_apply_patches_v12(
    payload: ExactPatchRequestV12,
    _user: AuthUser = Depends(get_current_user),
):
    try:
        return apply_exact_patches(
            payload.files,
            payload.patches,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )


@router.post("/api/owner/v12/evals/run")
async def evals_v12(
    live: bool = Query(False),
    limit: int = Query(400, ge=1, le=500),
    release: str = Query("v12", max_length=100),
    categories: str = Query(""),
    user: AuthUser = Depends(get_current_user),
):
    await require_owner(user)

    wanted = [
        item.strip()
        for item in categories.split(",")
        if item.strip()
    ] or None

    report = await run_eval(
        settings,
        release=release,
        live=live,
        categories=wanted,
        limit=limit,
        concurrency=int(
            getattr(settings, "v11_eval_concurrency", 3)
        ),
    )

    report["engine"] = "v12"
    report["note"] = (
        "V12 preserves the V11 benchmark corpus while adding "
        "stronger provider, citation, memory, sandbox and repair layers."
    )

    return report
