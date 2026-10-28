from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from app.services.chat_v10 import route_chat_v10
from app.v11 import store
from app.v11.research import run_research
from app.v11.scheduler import create_task as create_v11_task, next_run_from_cron, runtime_note
from app.v73.multi_agent import (
    TERMINAL_STATES as V73_TERMINAL_STATES,
    cancel_multi_agent_job,
    create_multi_agent_job,
    get_multi_agent_job,
)

_MARKER = "[V75]"
_ALLOWED_MODES = {"chat", "research", "multi_agent"}
_FINAL_STATUSES = {"completed", "cancelled", "error"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("run_at is required.")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("run_at must be a valid ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _encode_prompt(prompt: str, mode: str) -> str:
    cleaned = str(prompt or "").strip()
    selected = str(mode or "chat").strip().casefold()
    if selected not in _ALLOWED_MODES:
        raise ValueError("mode must be chat, research, or multi_agent.")
    if not cleaned:
        raise ValueError("Task prompt cannot be empty.")
    payload = {"version": "v75", "mode": selected, "prompt": cleaned[:12000]}
    return _MARKER + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def decode_prompt(value: Any) -> dict[str, str]:
    raw = str(value or "")
    if not raw.startswith(_MARKER):
        return {"mode": "chat", "prompt": raw.strip()}
    try:
        payload = json.loads(raw[len(_MARKER):])
    except Exception:
        return {"mode": "chat", "prompt": raw.strip()}
    if not isinstance(payload, dict):
        return {"mode": "chat", "prompt": raw.strip()}
    mode = str(payload.get("mode") or "chat").strip().casefold()
    prompt = str(payload.get("prompt") or "").strip()
    if mode not in _ALLOWED_MODES:
        mode = "chat"
    return {"mode": mode, "prompt": prompt}


def public_task(row: dict[str, Any]) -> dict[str, Any]:
    decoded = decode_prompt(row.get("prompt"))
    return {
        "id": str(row.get("id") or ""),
        "title": str(row.get("title") or ""),
        "prompt": decoded["prompt"],
        "mode": decoded["mode"],
        "run_at": row.get("run_at"),
        "cron": row.get("cron"),
        "status": str(row.get("status") or ""),
        "last_run_at": row.get("last_run_at"),
        "result": row.get("result"),
        "created_at": row.get("created_at"),
    }


def health_snapshot(settings: Any) -> dict[str, Any]:
    persistent = bool(store.configured(settings))
    return {
        "ok": True,
        "version": "v75",
        "name": "Vasuki Autonomous Tasks",
        "persistent_scheduler_available": persistent,
        "supported_modes": sorted(_ALLOWED_MODES),
        "features": [
            "persistent-one-time-tasks",
            "persistent-recurring-tasks",
            "pause-resume-cancel",
            "task-history-and-last-result",
            "chat-task-execution",
            "research-task-execution",
            "multi-agent-task-execution",
            "operations-center-task-management",
        ],
        "schedule_support": {
            "one_time_iso_timestamp": True,
            "every_n_minutes_cron": True,
            "daily_hour_minute_cron": True,
            "arbitrary_cron": False,
        },
        "event_triggers": {
            "available": False,
            "reason": "Connector event streams are not wired into the V75 scheduler yet.",
        },
        "delivery": {"in_app_task_result": True, "email_push_sms": False},
        "runtime": {
            "background_polling": True,
            "exact_wake_on_sleeping_free_host": False,
            "note": runtime_note(),
        },
        "safety": {
            "external_writes": False,
            "destructive_actions": False,
            "scheduled_browser_interactions": False,
            "payment_actions": False,
        },
        "new_database_migration_required": False,
        "new_api_key_required": False,
    }


async def create_task(
    settings: Any,
    *,
    user_id: str,
    title: str,
    prompt: str,
    mode: str = "chat",
    run_at: str | None = None,
    cron: str | None = None,
) -> dict[str, Any]:
    if not store.configured(settings):
        raise RuntimeError("Persistent scheduler storage is unavailable.")
    title_clean = str(title or "").strip()
    if not title_clean:
        raise ValueError("Task title cannot be empty.")
    if bool(run_at) == bool(cron):
        raise ValueError("Provide exactly one of run_at or cron.")

    effective_run_at: str | None = None
    effective_cron: str | None = None

    if cron:
        effective_cron = str(cron).strip()
        if not next_run_from_cron(effective_cron):
            raise ValueError("Unsupported cron. Use */N * * * * or M H * * *.")
    else:
        parsed = _parse_iso(str(run_at or ""))
        if parsed <= _utc_now():
            raise ValueError("run_at must be in the future.")
        effective_run_at = parsed.isoformat()

    row = await create_v11_task(
        settings,
        user_id=user_id,
        title=title_clean[:200],
        prompt=_encode_prompt(prompt, mode),
        run_at=effective_run_at,
        cron=effective_cron,
    )
    return public_task(row)


async def list_tasks(settings: Any, *, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    if not store.configured(settings):
        return []
    rows = await store.request(
        settings,
        "GET",
        "v11_scheduled_tasks",
        params={
            "user_id": f"eq.{user_id}",
            "select": "*",
            "order": "created_at.desc",
            "limit": str(max(1, min(100, int(limit)))),
        },
    )
    if not isinstance(rows, list):
        return []
    return [public_task(row) for row in rows if isinstance(row, dict)]


async def _get_raw_task(
    settings: Any, *, user_id: str, task_id: str
) -> dict[str, Any] | None:
    if not store.configured(settings):
        return None
    rows = await store.request(
        settings,
        "GET",
        "v11_scheduled_tasks",
        params={
            "id": f"eq.{task_id}",
            "user_id": f"eq.{user_id}",
            "select": "*",
            "limit": "1",
        },
    )
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    return None


async def _patch_task(
    settings: Any,
    *,
    user_id: str,
    task_id: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    rows = await store.request(
        settings,
        "PATCH",
        "v11_scheduled_tasks",
        params={"id": f"eq.{task_id}", "user_id": f"eq.{user_id}"},
        json_body=payload,
    )
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return public_task(rows[0])
    return None


async def pause_task(
    settings: Any, *, user_id: str, task_id: str
) -> dict[str, Any] | None:
    row = await _get_raw_task(settings, user_id=user_id, task_id=task_id)
    if row is None:
        return None
    if str(row.get("status") or "") != "scheduled":
        raise ValueError("Only scheduled tasks can be paused.")
    return await _patch_task(
        settings, user_id=user_id, task_id=task_id, payload={"status": "paused"}
    )


async def resume_task(
    settings: Any,
    *,
    user_id: str,
    task_id: str,
    run_at: str | None = None,
) -> dict[str, Any] | None:
    row = await _get_raw_task(settings, user_id=user_id, task_id=task_id)
    if row is None:
        return None
    if str(row.get("status") or "") != "paused":
        raise ValueError("Only paused tasks can be resumed.")

    cron = str(row.get("cron") or "").strip()
    payload: dict[str, Any] = {"status": "scheduled"}

    if cron:
        next_run = next_run_from_cron(cron)
        if not next_run:
            raise ValueError("Stored cron is no longer supported.")
        payload["run_at"] = next_run
    else:
        candidate = run_at or row.get("run_at")
        parsed = _parse_iso(str(candidate or ""))
        if parsed <= _utc_now():
            raise ValueError("A future run_at is required to resume this one-time task.")
        payload["run_at"] = parsed.isoformat()

    return await _patch_task(
        settings, user_id=user_id, task_id=task_id, payload=payload
    )


async def cancel_task(
    settings: Any, *, user_id: str, task_id: str
) -> dict[str, Any] | None:
    row = await _get_raw_task(settings, user_id=user_id, task_id=task_id)
    if row is None:
        return None
    if str(row.get("status") or "") in _FINAL_STATUSES:
        return public_task(row)
    return await _patch_task(
        settings, user_id=user_id, task_id=task_id, payload={"status": "cancelled"}
    )


async def _execute_multi_agent(
    settings: Any, *, user_id: str, prompt: str
) -> dict[str, Any]:
    started = await create_multi_agent_job(
        settings, user_id=user_id, goal=prompt, project_id=None
    )
    job_id = str(started.get("job_id") or "")
    if not job_id:
        raise RuntimeError("V73 multi-agent task did not return a job id.")

    for _ in range(180):
        state = await get_multi_agent_job(user_id=user_id, job_id=job_id)
        if state is None:
            raise RuntimeError("V73 multi-agent task disappeared.")
        status = str(state.get("status") or "")
        if status in V73_TERMINAL_STATES:
            if status != "succeeded":
                raise RuntimeError(
                    str(state.get("error") or state.get("message") or "Multi-agent task failed.")
                )
            result = state.get("result") if isinstance(state.get("result"), dict) else {}
            return {
                "answer": str(result.get("answer") or "")[:40000],
                "provider": str(result.get("provider") or "vasuki-multi-agent-v73"),
                "sources": result.get("sources") if isinstance(result.get("sources"), list) else [],
                "execution_proof": result.get("execution_proof"),
            }
        await asyncio.sleep(0.5)

    await cancel_multi_agent_job(user_id=user_id, job_id=job_id)
    raise RuntimeError("Scheduled multi-agent task exceeded the 90 second V75 limit.")


async def execute_scheduled_task(settings: Any, row: dict[str, Any]) -> dict[str, Any]:
    decoded = decode_prompt(row.get("prompt"))
    prompt = decoded["prompt"]
    mode = decoded["mode"]
    user_id = str(row.get("user_id") or "")

    if mode == "research":
        report = await run_research(prompt, settings)
        if not isinstance(report, dict):
            raise RuntimeError("Research task returned an invalid result.")
        return {
            "mode": mode,
            "answer": str(report.get("answer") or "")[:40000],
            "sources": report.get("sources") if isinstance(report.get("sources"), list) else [],
            "provider": str(report.get("provider") or "vasuki-research"),
        }

    if mode == "multi_agent":
        if not user_id:
            raise RuntimeError("Scheduled multi-agent task is missing user ownership.")
        result = await _execute_multi_agent(settings, user_id=user_id, prompt=prompt)
        return {"mode": mode, **result}

    answer, provider = await route_chat_v10(
        "auto", [{"role": "user", "content": prompt}], settings, ""
    )
    return {"mode": "chat", "answer": answer[:40000], "provider": provider}
