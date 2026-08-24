from __future__ import annotations

# VASUKI_V17_ASYNC_BUILD_JOBS

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

ProgressFn = Callable[[str, int, str], Awaitable[None]]
RunnerFn = Callable[[ProgressFn], Awaitable[dict[str, Any]]]


@dataclass
class BuildJob:
    id: str
    user_id: str
    status: str = "queued"
    stage: str = "queued"
    progress: int = 0
    message: str = "Build queued"
    error: str = ""
    result: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    task: asyncio.Task | None = None

    def snapshot(self, *, include_result: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.status != "failed",
            "job_id": self.id,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "message": self.message,
            "error": self.error or None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if include_result and self.status == "succeeded":
            payload["result"] = self.result
        return payload


_JOBS: dict[str, BuildJob] = {}
_LOCK = asyncio.Lock()


async def _cleanup(ttl_seconds: int = 3600) -> None:
    cutoff = time.time() - max(300, ttl_seconds)
    async with _LOCK:
        stale = [
            job_id
            for job_id, job in _JOBS.items()
            if job.updated_at < cutoff
            and job.status in {"succeeded", "failed", "cancelled"}
        ]
        for job_id in stale:
            _JOBS.pop(job_id, None)


async def create_build_job(
    *,
    user_id: str,
    runner: RunnerFn,
    ttl_seconds: int = 3600,
) -> dict[str, Any]:
    await _cleanup(ttl_seconds)

    job = BuildJob(
        id=uuid.uuid4().hex,
        user_id=user_id,
    )

    async with _LOCK:
        active_for_user = sum(
            1
            for value in _JOBS.values()
            if value.user_id == user_id
            and value.status in {"queued", "running"}
        )
        if active_for_user >= 2:
            raise RuntimeError(
                "You already have two active builds. Stop one or wait for it to finish."
            )
        _JOBS[job.id] = job

    async def progress(stage: str, value: int, message: str) -> None:
        async with _LOCK:
            current = _JOBS.get(job.id)
            if not current or current.status == "cancelled":
                return
            current.stage = str(stage or "working")[:80]
            current.progress = max(0, min(100, int(value)))
            current.message = str(message or "Working…")[:500]
            current.updated_at = time.time()

    async def execute() -> None:
        try:
            await progress("starting", 2, "Starting autonomous build")
            async with _LOCK:
                current = _JOBS.get(job.id)
                if current:
                    current.status = "running"
                    current.updated_at = time.time()

            result = await runner(progress)

            async with _LOCK:
                current = _JOBS.get(job.id)
                if not current or current.status == "cancelled":
                    return
                current.status = "succeeded"
                current.stage = "ready"
                current.progress = 100
                current.message = "Project ready"
                current.result = result
                current.updated_at = time.time()
        except asyncio.CancelledError:
            async with _LOCK:
                current = _JOBS.get(job.id)
                if current:
                    current.status = "cancelled"
                    current.stage = "cancelled"
                    current.message = "Build cancelled"
                    current.updated_at = time.time()
            raise
        except Exception as exc:
            async with _LOCK:
                current = _JOBS.get(job.id)
                if current:
                    current.status = "failed"
                    current.error = str(exc)[:3000]
                    current.message = (
                        f"Build failed during {current.stage}: {str(exc)[:700]}"
                    )
                    current.updated_at = time.time()

    task = asyncio.create_task(execute(), name=f"vasuki-build-{job.id[:8]}")
    async with _LOCK:
        current = _JOBS.get(job.id)
        if current:
            current.task = task

    return job.snapshot(include_result=False)


async def get_build_job(
    *,
    user_id: str,
    job_id: str,
    ttl_seconds: int = 3600,
) -> dict[str, Any] | None:
    await _cleanup(ttl_seconds)
    async with _LOCK:
        job = _JOBS.get(job_id)
        if not job or job.user_id != user_id:
            return None
        return job.snapshot(include_result=True)


async def cancel_build_job(
    *,
    user_id: str,
    job_id: str,
) -> dict[str, Any] | None:
    async with _LOCK:
        job = _JOBS.get(job_id)
        if not job or job.user_id != user_id:
            return None
        if job.status in {"succeeded", "failed", "cancelled"}:
            return job.snapshot(include_result=False)
        job.status = "cancelled"
        job.stage = "cancelled"
        job.message = "Build cancelled"
        job.updated_at = time.time()
        task = job.task

    if task and not task.done():
        task.cancel()

    return job.snapshot(include_result=False)


async def shutdown_build_jobs() -> None:
    async with _LOCK:
        tasks = [
            job.task
            for job in _JOBS.values()
            if job.task and not job.task.done()
        ]
    for task in tasks:
        task.cancel()


def jobs_health() -> dict[str, Any]:
    counts = {
        "queued": 0,
        "running": 0,
        "succeeded": 0,
        "failed": 0,
        "cancelled": 0,
    }
    for job in list(_JOBS.values()):
        if job.status in counts:
            counts[job.status] += 1
    return {
        "engine": "in-process-async-jobs",
        "counts": counts,
        "result_ttl_seconds": 3600,
        "per_user_active_limit": 2,
    }
