from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.v11 import store


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()

    if not raw:
        return None

    try:
        result = datetime.fromisoformat(
            raw.replace("Z", "+00:00")
        )
    except ValueError:
        return None

    if result.tzinfo is None:
        result = result.replace(
            tzinfo=timezone.utc
        )

    return result.astimezone(
        timezone.utc
    )


async def proactive_snapshot(
    settings: Any,
    *,
    user_id: str,
    horizon_minutes: int | None = None,
) -> dict[str, Any]:
    if not store.configured(settings):
        return {
            "ok": True,
            "version": "v79",
            "storage_available": False,
            "nudges": [],
            "checked_tasks": 0,
        }

    default_horizon = int(
        getattr(
            settings,
            "v79_proactive_horizon_minutes",
            180,
        )
        or 180
    )

    horizon = int(
        horizon_minutes
        if horizon_minutes is not None
        else default_horizon
    )

    horizon = max(
        15,
        min(
            horizon,
            1440,
        ),
    )

    now = _utc_now()
    horizon_end = now + timedelta(
        minutes=horizon
    )

    rows = await store.request(
        settings,
        "GET",
        "v11_scheduled_tasks",
        params={
            "user_id": f"eq.{user_id}",
            "select": "*",
            "order": "run_at.asc",
            "limit": "100",
        },
    )

    if not isinstance(rows, list):
        rows = []

    nudges: list[dict[str, Any]] = []

    for row in rows:
        status = str(
            row.get("status") or ""
        ).strip().casefold()

        title = str(
            row.get("title")
            or "Scheduled task"
        ).strip()

        task_id = str(
            row.get("id") or ""
        ).strip()

        run_at = _parse_datetime(
            row.get("run_at")
        )

        if status == "error":
            nudges.append(
                {
                    "kind": "task_failed",
                    "priority": "high",
                    "task_id": task_id,
                    "title": title,
                    "message": (
                        f"Scheduled task failed: "
                        f"{title}"
                    ),
                }
            )

            continue

        if status != "scheduled":
            continue

        if run_at is None:
            continue

        if run_at <= now:
            nudges.append(
                {
                    "kind": "task_due",
                    "priority": "high",
                    "task_id": task_id,
                    "title": title,
                    "run_at": run_at.isoformat(),
                    "message": (
                        f"Task is due now: "
                        f"{title}"
                    ),
                }
            )

            continue

        if run_at <= horizon_end:
            seconds_left = (
                run_at - now
            ).total_seconds()

            minutes_left = max(
                1,
                int(
                    seconds_left // 60
                ),
            )

            nudges.append(
                {
                    "kind": "task_upcoming",
                    "priority": "normal",
                    "task_id": task_id,
                    "title": title,
                    "run_at": run_at.isoformat(),
                    "minutes_until": minutes_left,
                    "message": (
                        f"Upcoming in "
                        f"{minutes_left} min: "
                        f"{title}"
                    ),
                }
            )

    priority_rank = {
        "high": 0,
        "normal": 1,
        "low": 2,
    }

    nudges.sort(
        key=lambda item: (
            priority_rank.get(
                str(
                    item.get("priority")
                    or ""
                ),
                9,
            ),
            str(
                item.get("run_at")
                or ""
            ),
        )
    )

    return {
        "ok": True,
        "version": "v79",
        "storage_available": True,
        "horizon_minutes": horizon,
        "checked_tasks": len(rows),
        "nudges": nudges[:20],
        "llm_polling": False,
        "design": (
            "deterministic checks first; "
            "AI reasoning only when "
            "something actionable exists"
        ),
    }


def health_snapshot(
    settings: Any,
) -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v79",
        "name": (
            "Vasuki Proactive Event Layer"
        ),
        "storage_available": bool(
            store.configured(settings)
        ),
        "checks": [
            "due-scheduled-task",
            "upcoming-scheduled-task",
            "failed-scheduled-task",
        ],
        "llm_every_few_minutes": False,
        "external_actions": False,
        "destructive_actions": False,
        "next_connectors": [
            "calendar-upcoming-events",
            "pending-files-jobs",
            "ci-failure-events",
            "follow-up-deadlines",
        ],
    }
