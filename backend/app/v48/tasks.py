from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.v11 import store
from app.v11.scheduler import next_run_from_cron, now_iso


async def list_tasks(settings: Any, *, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
    if not store.configured(settings):
        return []
    return await store.request(
        settings,
        "GET",
        "v11_scheduled_tasks",
        params={
            "user_id": f"eq.{user_id}",
            "select": "*",
            "order": "created_at.desc",
            "limit": str(max(1, min(200, int(limit)))),
        },
    ) or []


async def update_task(
    settings: Any,
    *,
    user_id: str,
    task_id: str,
    status: str | None = None,
    title: str | None = None,
    prompt: str | None = None,
    run_at: str | None = None,
    cron: str | None = None,
) -> dict[str, Any] | None:
    if not store.configured(settings):
        return None
    patch: dict[str, Any] = {}
    if status is not None:
        value = status.strip().lower()
        if value not in {"scheduled", "paused"}:
            raise ValueError("Task status must be scheduled or paused.")
        patch["status"] = value
    if title is not None:
        patch["title"] = title[:200]
    if prompt is not None:
        patch["prompt"] = prompt[:12000]
    if cron is not None:
        if cron.strip():
            next_run = next_run_from_cron(cron)
            if not next_run:
                raise ValueError("Unsupported cron. Use */N * * * * or M H * * *.")
            patch["cron"] = cron.strip()
            patch["run_at"] = next_run
        else:
            patch["cron"] = None
    if run_at is not None:
        value = run_at.strip()
        if value:
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError as exc:
                raise ValueError("run_at must be a valid ISO-8601 date/time.") from exc
            patch["run_at"] = value
    if status == "scheduled" and "run_at" not in patch and cron is None:
        patch.setdefault("run_at", now_iso())
    if not patch:
        raise ValueError("No task changes were provided.")
    rows = await store.request(
        settings,
        "PATCH",
        "v11_scheduled_tasks",
        params={"id": f"eq.{task_id}", "user_id": f"eq.{user_id}"},
        json_body=patch,
    )
    return rows[0] if isinstance(rows, list) and rows else None


async def delete_task(settings: Any, *, user_id: str, task_id: str) -> bool:
    if not store.configured(settings):
        return False
    await store.request(
        settings,
        "DELETE",
        "v11_scheduled_tasks",
        params={"id": f"eq.{task_id}", "user_id": f"eq.{user_id}"},
    )
    return True
