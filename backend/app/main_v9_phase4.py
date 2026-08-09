from __future__ import annotations

import asyncio
from typing import Any

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field

import app.main_v9_phase3 as phase3
from app.auth import AuthUser, get_current_user
from app.services.jobs_v9 import (
    SUPPORTED_JOB_KINDS,
    cancel_pending_job,
    count_user_jobs,
    create_job,
    list_jobs,
    start_job_worker,
    stop_job_worker,
    validate_job_payload,
)
from app.services.plans_v2 import get_plan_status
from app.services.platform_v9_phase4 import (
    evaluate_job_policy,
    feature_assignments,
    list_notifications,
    log_experiment_event,
    mark_all_notifications_read,
    mark_notification_read,
    owner_platform_snapshot,
    plan_policy,
    upsert_feature_flag,
    user_usage_snapshot,
)

app = phase3.app
settings = phase3.settings


class BackgroundJobRequest(BaseModel):
    kind: str = Field(..., min_length=3, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)


class FeatureFlagUpdate(BaseModel):
    enabled: bool = True
    rollout_percent: int = Field(default=100, ge=0, le=100)
    variants: dict[str, Any] = Field(default_factory=dict)
    description: str = Field(default="", max_length=500)


class ExperimentConversionRequest(BaseModel):
    variant: str = Field(..., min_length=1, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


async def _phase4_startup() -> None:
    start_job_worker(settings)


async def _phase4_shutdown() -> None:
    await stop_job_worker()


app.router.add_event_handler("startup", _phase4_startup)
app.router.add_event_handler("shutdown", _phase4_shutdown)


async def _user_platform(
    current_user: AuthUser,
    *,
    days: int = 30,
) -> dict[str, Any]:
    status = await get_plan_status(current_user, settings)
    usage_task = asyncio.create_task(
        user_usage_snapshot(settings, user_id=current_user.id, days=days)
    )
    jobs_task = asyncio.create_task(
        list_jobs(settings, user_id=current_user.id, limit=80)
    )
    notifications_task = asyncio.create_task(
        list_notifications(settings, user_id=current_user.id, limit=80)
    )
    flags_task = asyncio.create_task(
        feature_assignments(settings, current_user.id)
    )
    usage, jobs, notifications, flags = await asyncio.gather(
        usage_task,
        jobs_task,
        notifications_task,
        flags_task,
    )
    experiments = {
        key: value["variant"]
        for key, value in flags.items()
        if value.get("enabled") and value.get("variant")
    }
    return {
        "plan": status.to_dict(),
        "policy": plan_policy(status.plan),
        "usage": usage,
        "jobs": jobs,
        "notifications": notifications,
        "features": flags,
        "experiments": experiments,
    }


@app.get("/api/platform/v9/snapshot")
async def platform_snapshot(
    days: int = Query(30, ge=1, le=90),
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    data = await _user_platform(current_user, days=days)
    return {"ok": True, **data}


@app.post("/api/jobs/v9")
async def submit_background_job(
    payload: BackgroundJobRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        clean_payload = validate_job_payload(payload.kind, payload.payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    status = await get_plan_status(current_user, settings)
    daily_count, active_count = await count_user_jobs(
        settings,
        user_id=current_user.id,
    )
    allowed, reason, policy = evaluate_job_policy(
        plan=status.plan,
        kind=payload.kind,
        payload=clean_payload,
        daily_count=daily_count,
        active_count=active_count,
    )
    if not allowed:
        raise HTTPException(status_code=403, detail=reason)
    try:
        job = await create_job(
            settings,
            user_id=current_user.id,
            kind=payload.kind,
            payload=clean_payload,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:1200]) from exc
    return {
        "ok": True,
        "job": job,
        "policy": policy,
        "usage": {
            "daily_before_submit": daily_count,
            "active_before_submit": active_count,
        },
    }


@app.get("/api/jobs/v9")
async def my_background_jobs(
    limit: int = Query(80, ge=1, le=200),
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "jobs": await list_jobs(
            settings,
            user_id=current_user.id,
            limit=limit,
        )
    }


@app.delete("/api/jobs/v9/{job_id}")
async def cancel_background_job(
    job_id: str,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "ok": await cancel_pending_job(
            settings,
            user_id=current_user.id,
            job_id=job_id,
        ),
        "note": "Only pending jobs can be cancelled. A provider call already running is not force-killed.",
    }


@app.get("/api/notifications/v9")
async def my_notifications(
    limit: int = Query(80, ge=1, le=200),
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return await list_notifications(settings, user_id=current_user.id, limit=limit)


@app.patch("/api/notifications/v9/{notification_id}/read")
async def read_notification(
    notification_id: str,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "ok": await mark_notification_read(
            settings,
            user_id=current_user.id,
            notification_id=notification_id,
        )
    }


@app.post("/api/notifications/v9/read-all")
async def read_all_notifications(
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "ok": await mark_all_notifications_read(
            settings,
            user_id=current_user.id,
        )
    }


@app.get("/api/usage/v9")
async def my_usage(
    days: int = Query(30, ge=1, le=90),
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "ok": True,
        **await user_usage_snapshot(
            settings,
            user_id=current_user.id,
            days=days,
        ),
    }


@app.get("/api/plan/policy/v3")
async def my_plan_policy(
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    status = await get_plan_status(current_user, settings)
    daily_count, active_count = await count_user_jobs(settings, user_id=current_user.id)
    return {
        "ok": True,
        "status": status.to_dict(),
        "policy": plan_policy(status.plan),
        "current": {
            "background_jobs_today": daily_count,
            "active_background_jobs": active_count,
        },
    }


@app.get("/api/features/v9/phase4")
async def my_phase4_features(
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    flags = await feature_assignments(settings, current_user.id)
    experiments = {
        key: value["variant"]
        for key, value in flags.items()
        if value.get("enabled") and value.get("variant")
    }
    for experiment, variant in experiments.items():
        asyncio.create_task(
            log_experiment_event(
                settings,
                user_id=current_user.id,
                experiment=experiment,
                variant=str(variant),
                event="exposure",
                metadata={"surface": "feature_endpoint"},
            )
        )
    return {
        "ok": True,
        "flags": flags,
        "experiments": experiments,
    }


@app.post("/api/experiments/v9/{experiment}/exposure")
async def record_experiment_exposure(
    experiment: str,
    payload: ExperimentConversionRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    asyncio.create_task(
        log_experiment_event(
            settings,
            user_id=current_user.id,
            experiment=experiment,
            variant=payload.variant,
            event="exposure",
            metadata=payload.metadata,
        )
    )
    return {"ok": True}


@app.post("/api/experiments/v9/{experiment}/conversion")
async def record_experiment_conversion(
    experiment: str,
    payload: ExperimentConversionRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    asyncio.create_task(
        log_experiment_event(
            settings,
            user_id=current_user.id,
            experiment=experiment,
            variant=payload.variant,
            event="conversion",
            metadata=payload.metadata,
        )
    )
    return {"ok": True}


@app.get("/api/owner/platform/v9")
async def owner_platform(
    days: int = Query(30, ge=1, le=90),
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    status = await get_plan_status(current_user, settings)
    if not status.is_owner:
        raise HTTPException(status_code=403, detail="Owner access required.")
    return {
        "ok": True,
        **await owner_platform_snapshot(settings, days=days),
    }


@app.patch("/api/owner/features/v9/{key}")
async def owner_update_feature(
    key: str,
    payload: FeatureFlagUpdate,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    status = await get_plan_status(current_user, settings)
    if not status.is_owner:
        raise HTTPException(status_code=403, detail="Owner access required.")
    try:
        row = await upsert_feature_flag(
            settings,
            key=key,
            enabled=payload.enabled,
            rollout_percent=payload.rollout_percent,
            variants=payload.variants,
            description=payload.description,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "flag": row}


@app.get("/health/v9-phase4")
async def health_v9_phase4() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v9-phase4",
        "background_job_queue": True,
        "job_progress_ui_api": True,
        "notification_center": True,
        "user_usage_dashboard": True,
        "owner_cost_quota_dashboard": True,
        "plan_policy_engine_v3": True,
        "feature_flags_v3": True,
        "ab_testing": True,
        "supported_background_jobs": sorted(SUPPORTED_JOB_KINDS),
        "cost_note": "Cost totals are only reported when runtime/provider metadata includes cost_usd or estimated_cost_usd; unknown costs are never invented.",
        "worker_note": "Jobs are persisted in Supabase and claimed atomically with SKIP LOCKED. Running provider calls are not force-cancelled.",
    }
