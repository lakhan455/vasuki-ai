from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.services.analytics_v8 import _base, _headers, configured, log_usage
from app.services.artifacts_v8 import save_artifact, signed_url
from app.services.coding_agent_v9 import generate_coding_plan
from app.services.image_studio_v9 import generate_studio_image
from app.services.platform_v9_phase4 import create_notification


SUPPORTED_JOB_KINDS = {
    "image.generate",
    "image.variations",
    "project.code.patch",
    "project.tests.generate",
    "project.debug",
}

WORKER_ID = f"{os.getenv('RENDER_INSTANCE_ID', 'vasuki')}-{uuid.uuid4().hex[:8]}"
_worker_task: asyncio.Task[Any] | None = None


def validate_job_payload(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    clean_kind = str(kind or "").strip()
    if clean_kind not in SUPPORTED_JOB_KINDS:
        raise ValueError(f"Unsupported background job kind: {clean_kind}")

    value = payload if isinstance(payload, dict) else {}
    if clean_kind in {"image.generate", "image.variations"}:
        prompt = str(value.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("Image background jobs require a prompt.")
        if len(prompt) > 5000:
            raise ValueError("Image prompt must be 5,000 characters or shorter.")
        clean = {
            "prompt": prompt,
            "preset": str(value.get("preset") or "none")[:40],
            "aspect_ratio": str(value.get("aspect_ratio") or "square")[:40],
        }
        if clean_kind == "image.variations":
            try:
                count = int(value.get("count") or 4)
            except Exception:
                count = 4
            clean["count"] = max(2, min(count, 4))
        return clean

    project_id = str(value.get("project_id") or "").strip()
    instruction = str(value.get("instruction") or "").strip()
    if not project_id:
        raise ValueError("Project background jobs require project_id.")
    if not instruction:
        raise ValueError("Project background jobs require an instruction.")
    clean = {
        "project_id": project_id,
        "instruction": instruction[:12000],
        "target_paths": [
            str(item)[:260]
            for item in (value.get("target_paths") or [])
            if str(item).strip()
        ][:30],
    }
    if clean_kind == "project.debug":
        error_log = str(value.get("error_log") or "").strip()
        if not error_log:
            raise ValueError("Project debug jobs require error_log.")
        clean["error_log"] = error_log[:20000]
    return clean


async def create_job(
    settings: Settings,
    *,
    user_id: str,
    kind: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if not configured(settings):
        raise RuntimeError("Background jobs require Supabase.")
    clean = validate_job_payload(kind, payload)
    body = {
        "user_id": user_id,
        "kind": kind,
        "status": "pending",
        "progress": 0,
        "input": clean,
        "output": {},
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{_base(settings)}/rest/v1/background_jobs_v9",
            headers=_headers(settings, representation=True),
            json=body,
        )
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("Background job could not be created.")
    return rows[0]


async def list_jobs(
    settings: Settings,
    *,
    user_id: str,
    limit: int = 80,
) -> list[dict[str, Any]]:
    if not configured(settings):
        return []
    safe_limit = max(1, min(int(limit), 200))
    url = (
        f"{_base(settings)}/rest/v1/background_jobs_v9"
        f"?user_id=eq.{quote(user_id)}"
        "&select=id,kind,status,progress,input,output,error,attempts,created_at,updated_at,finished_at"
        "&order=created_at.desc"
        f"&limit={safe_limit}"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=_headers(settings))
    response.raise_for_status()
    value = response.json()
    return value if isinstance(value, list) else []


async def count_user_jobs(settings: Settings, *, user_id: str) -> tuple[int, int]:
    if not configured(settings):
        return 0, 0
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    daily_url = (
        f"{_base(settings)}/rest/v1/background_jobs_v9"
        f"?user_id=eq.{quote(user_id)}"
        f"&created_at=gte.{quote(today)}"
        "&select=id"
        "&limit=1000"
    )
    active_url = (
        f"{_base(settings)}/rest/v1/background_jobs_v9"
        f"?user_id=eq.{quote(user_id)}"
        "&status=in.(pending,running)"
        "&select=id"
        "&limit=1000"
    )
    async with httpx.AsyncClient(timeout=8.0) as client:
        daily_response, active_response = await asyncio.gather(
            client.get(daily_url, headers=_headers(settings)),
            client.get(active_url, headers=_headers(settings)),
        )
    daily_rows = daily_response.json() if daily_response.is_success else []
    active_rows = active_response.json() if active_response.is_success else []
    return (
        len(daily_rows) if isinstance(daily_rows, list) else 0,
        len(active_rows) if isinstance(active_rows, list) else 0,
    )


async def cancel_pending_job(settings: Settings, *, user_id: str, job_id: str) -> bool:
    if not configured(settings):
        return False
    payload = {
        "status": "cancelled",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    url = (
        f"{_base(settings)}/rest/v1/background_jobs_v9"
        f"?id=eq.{quote(job_id)}&user_id=eq.{quote(user_id)}&status=eq.pending"
    )
    headers = dict(_headers(settings, representation=True))
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.patch(url, headers=headers, json=payload)
    if not response.is_success:
        return False
    rows = response.json()
    return isinstance(rows, list) and bool(rows)


async def _patch_job(settings: Settings, job_id: str, payload: dict[str, Any]) -> None:
    if not configured(settings):
        return
    body = {**payload, "updated_at": datetime.now(timezone.utc).isoformat()}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            await client.patch(
                f"{_base(settings)}/rest/v1/background_jobs_v9?id=eq.{quote(job_id)}",
                headers=_headers(settings),
                json=body,
            )
    except Exception:
        return


async def _claim_job(settings: Settings) -> dict[str, Any] | None:
    if not configured(settings):
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{_base(settings)}/rest/v1/rpc/claim_vasuki_job_v9",
                headers=_headers(settings),
                json={"p_worker_id": WORKER_ID},
            )
        if not response.is_success:
            return None
        rows = response.json()
        if isinstance(rows, list) and rows:
            return rows[0]
    except Exception:
        return None
    return None


async def _artifact_for_result(
    settings: Settings,
    *,
    user_id: str,
    result: dict[str, Any],
    prompt: str,
    name: str,
) -> dict[str, Any] | None:
    url = str(result.get("url") or "")
    if not url:
        return None
    mime = "image/png" if url.startswith("data:image/png") else "image/jpeg"
    artifact = await save_artifact(
        settings,
        user_id=user_id,
        name=name,
        artifact_type="image",
        mime_type=mime,
        data_url=url if url.startswith("data:") else None,
        external_url=url if url.startswith("http") else None,
        prompt=prompt,
        provider=str(result.get("provider") or ""),
        retention_days=30,
    )
    if not artifact:
        return None
    if artifact.get("storage_path"):
        artifact["download_url"] = await signed_url(settings, str(artifact["storage_path"]))
    elif artifact.get("external_url"):
        artifact["download_url"] = artifact["external_url"]
    return artifact


def _compact_image_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in result.items()
        if key not in {"url", "enhanced_prompt"}
    }


async def _run_image_generate(settings: Settings, job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("input") if isinstance(job.get("input"), dict) else {}
    await _patch_job(settings, str(job["id"]), {"progress": 20})
    result = await generate_studio_image(
        settings,
        prompt=str(payload.get("prompt") or ""),
        preset=str(payload.get("preset") or "none"),
        aspect_ratio=str(payload.get("aspect_ratio") or "square"),
    )
    await _patch_job(settings, str(job["id"]), {"progress": 82})
    artifact = await _artifact_for_result(
        settings,
        user_id=str(job["user_id"]),
        result=result,
        prompt=str(payload.get("prompt") or ""),
        name="Vasuki background image",
    )
    return {
        "result": _compact_image_result(result),
        "artifact": artifact,
    }


async def _run_image_variations(settings: Settings, job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("input") if isinstance(job.get("input"), dict) else {}
    count = max(2, min(int(payload.get("count") or 4), 4))
    items = []
    for index in range(1, count + 1):
        await _patch_job(
            settings,
            str(job["id"]),
            {"progress": 10 + round(((index - 1) / count) * 75)},
        )
        result = await generate_studio_image(
            settings,
            prompt=str(payload.get("prompt") or ""),
            preset=str(payload.get("preset") or "none"),
            aspect_ratio=str(payload.get("aspect_ratio") or "square"),
            variation_index=index,
        )
        artifact = await _artifact_for_result(
            settings,
            user_id=str(job["user_id"]),
            result=result,
            prompt=str(payload.get("prompt") or ""),
            name=f"Vasuki background variation {index}",
        )
        items.append({
            "index": index,
            "result": _compact_image_result(result),
            "artifact": artifact,
        })
    return {"items": items, "count": count}


async def _run_project_job(settings: Settings, job: dict[str, Any], mode: str) -> dict[str, Any]:
    payload = job.get("input") if isinstance(job.get("input"), dict) else {}
    await _patch_job(settings, str(job["id"]), {"progress": 20})
    result = await generate_coding_plan(
        settings,
        user_id=str(job["user_id"]),
        project_id=str(payload.get("project_id") or ""),
        instruction=str(payload.get("instruction") or ""),
        target_paths=list(payload.get("target_paths") or []),
        mode=mode,
        debug_log=str(payload.get("error_log") or "") if mode == "debug" else "",
    )
    await _patch_job(settings, str(job["id"]), {"progress": 88})
    return result


async def execute_job(settings: Settings, job: dict[str, Any]) -> dict[str, Any]:
    kind = str(job.get("kind") or "")
    if kind == "image.generate":
        return await _run_image_generate(settings, job)
    if kind == "image.variations":
        return await _run_image_variations(settings, job)
    if kind == "project.code.patch":
        return await _run_project_job(settings, job, "patch")
    if kind == "project.tests.generate":
        return await _run_project_job(settings, job, "tests")
    if kind == "project.debug":
        return await _run_project_job(settings, job, "debug")
    raise ValueError(f"Unsupported background job kind: {kind}")


async def worker_loop(settings: Settings) -> None:
    while True:
        try:
            job = await _claim_job(settings)
            if not job:
                await asyncio.sleep(2.0)
                continue
            job_id = str(job.get("id") or "")
            user_id = str(job.get("user_id") or "")
            kind = str(job.get("kind") or "background job")
            try:
                await _patch_job(settings, job_id, {"progress": 8})
                output = await execute_job(settings, job)
                await _patch_job(
                    settings,
                    job_id,
                    {
                        "status": "succeeded",
                        "progress": 100,
                        "output": output,
                        "error": None,
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                await create_notification(
                    settings,
                    user_id=user_id,
                    title="Background job completed",
                    body=f"{kind} completed successfully.",
                    kind="success",
                    action_url="/operations",
                    metadata={"job_id": job_id, "job_kind": kind},
                )
                await log_usage(
                    settings,
                    feature="background_job",
                    user_id=user_id,
                    status="ok",
                    metadata={"job_id": job_id, "job_kind": kind},
                )
            except Exception as exc:
                await _patch_job(
                    settings,
                    job_id,
                    {
                        "status": "failed",
                        "progress": 100,
                        "error": str(exc)[:1800],
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                await create_notification(
                    settings,
                    user_id=user_id,
                    title="Background job failed",
                    body=f"{kind} failed: {str(exc)[:500]}",
                    kind="error",
                    action_url="/operations",
                    metadata={"job_id": job_id, "job_kind": kind},
                )
                await log_usage(
                    settings,
                    feature="background_job",
                    user_id=user_id,
                    status="error",
                    metadata={"job_id": job_id, "job_kind": kind, "error": str(exc)[:500]},
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(2.0)


def start_job_worker(settings: Settings) -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    if not configured(settings):
        return
    _worker_task = asyncio.create_task(worker_loop(settings))


async def stop_job_worker() -> None:
    global _worker_task
    task = _worker_task
    _worker_task = None
    if not task:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
