from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from app.services.project_kb_v9 import list_project_files
from app.services.project_memory_v8 import (
    add_project_memory,
    delete_project_memory,
    get_project,
    list_project_memories,
)

PREFIX = "[V71]"
KINDS = {"goal", "decision", "task", "last_work", "repo"}
TASK_STATUSES = {"pending", "in_progress", "blocked", "done"}
TASK_PRIORITIES = {"low", "normal", "high", "critical"}


def _clean(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def encode_entry(kind: str, payload: dict[str, Any]) -> str:
    normalized_kind = str(kind or "").strip().casefold()
    if normalized_kind not in KINDS:
        raise ValueError("Unsupported Project Brain item kind.")
    value = PREFIX + json.dumps(
        {"kind": normalized_kind, **payload},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(value) > 1180:
        raise ValueError("Project Brain item is too long.")
    return value


def parse_entry(row: dict[str, Any]) -> dict[str, Any] | None:
    text = str(row.get("memory_text") or "").strip()
    source = str(row.get("source") or "").strip().casefold()
    if not text.startswith(PREFIX) and source != "v71":
        return None
    raw = text[len(PREFIX):].strip() if text.startswith(PREFIX) else text
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    kind = str(payload.get("kind") or "").strip().casefold()
    if kind not in KINDS:
        return None
    return {
        "id": str(row.get("id") or ""),
        "kind": kind,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        **payload,
    }


async def list_entries(
    settings: Any,
    *,
    user_id: str,
    project_id: str,
) -> list[dict[str, Any]]:
    rows = await list_project_memories(
        settings,
        user_id=user_id,
        project_id=project_id,
        limit=200,
    )
    entries: list[dict[str, Any]] = []
    for row in rows:
        parsed = parse_entry(row)
        if parsed:
            entries.append(parsed)
    return entries


async def _delete_kind(
    settings: Any,
    *,
    user_id: str,
    project_id: str,
    kind: str,
) -> None:
    for item in await list_entries(
        settings,
        user_id=user_id,
        project_id=project_id,
    ):
        if item.get("kind") == kind:
            await delete_project_memory(
                settings,
                user_id=user_id,
                project_id=project_id,
                memory_id=str(item.get("id") or ""),
            )


async def set_goal(
    settings: Any,
    *,
    user_id: str,
    project_id: str,
    text: str,
) -> dict[str, Any]:
    value = _clean(text, 900)
    if len(value) < 3:
        raise ValueError("Project goal must contain at least 3 characters.")
    await _delete_kind(
        settings,
        user_id=user_id,
        project_id=project_id,
        kind="goal",
    )
    row = await add_project_memory(
        settings,
        user_id=user_id,
        project_id=project_id,
        memory_text=encode_entry("goal", {"text": value}),
        source="v71",
        confidence=1.0,
    )
    return parse_entry(row) or {"kind": "goal", "text": value}


async def set_last_work(
    settings: Any,
    *,
    user_id: str,
    project_id: str,
    summary: str,
    next_step: str = "",
) -> dict[str, Any]:
    clean_summary = _clean(summary, 700)
    clean_next = _clean(next_step, 320)
    if len(clean_summary) < 3:
        raise ValueError("Last-work summary must contain at least 3 characters.")
    await _delete_kind(
        settings,
        user_id=user_id,
        project_id=project_id,
        kind="last_work",
    )
    row = await add_project_memory(
        settings,
        user_id=user_id,
        project_id=project_id,
        memory_text=encode_entry(
            "last_work",
            {"summary": clean_summary, "next_step": clean_next},
        ),
        source="v71",
        confidence=1.0,
    )
    return parse_entry(row) or {
        "kind": "last_work",
        "summary": clean_summary,
        "next_step": clean_next,
    }


async def add_decision(
    settings: Any,
    *,
    user_id: str,
    project_id: str,
    title: str,
    rationale: str = "",
) -> dict[str, Any]:
    clean_title = _clean(title, 420)
    clean_reason = _clean(rationale, 650)
    if len(clean_title) < 3:
        raise ValueError("Decision title must contain at least 3 characters.")
    row = await add_project_memory(
        settings,
        user_id=user_id,
        project_id=project_id,
        memory_text=encode_entry(
            "decision",
            {"title": clean_title, "rationale": clean_reason},
        ),
        source="v71",
        confidence=1.0,
    )
    return parse_entry(row) or {
        "kind": "decision",
        "title": clean_title,
        "rationale": clean_reason,
    }


async def add_repo(
    settings: Any,
    *,
    user_id: str,
    project_id: str,
    label: str,
    url: str,
) -> dict[str, Any]:
    clean_label = _clean(label, 180)
    clean_url = _clean(url, 700)
    if not re.match(
        r"^https://(?:www\.)?github\.com/[^/\s]+/[^/\s]+/?$",
        clean_url,
        re.I,
    ):
        raise ValueError("Repository must be a GitHub repository URL.")
    if not clean_label:
        clean_label = clean_url.rstrip("/").rsplit("/", 1)[-1]
    row = await add_project_memory(
        settings,
        user_id=user_id,
        project_id=project_id,
        memory_text=encode_entry(
            "repo",
            {"label": clean_label, "url": clean_url.rstrip("/")},
        ),
        source="v71",
        confidence=1.0,
    )
    return parse_entry(row) or {
        "kind": "repo",
        "label": clean_label,
        "url": clean_url.rstrip("/"),
    }


async def add_task(
    settings: Any,
    *,
    user_id: str,
    project_id: str,
    title: str,
    status: str = "pending",
    priority: str = "normal",
    notes: str = "",
) -> dict[str, Any]:
    clean_title = _clean(title, 420)
    clean_status = str(status or "pending").strip().casefold()
    clean_priority = str(priority or "normal").strip().casefold()
    clean_notes = _clean(notes, 560)
    if len(clean_title) < 3:
        raise ValueError("Task title must contain at least 3 characters.")
    if clean_status not in TASK_STATUSES:
        raise ValueError("Unsupported task status.")
    if clean_priority not in TASK_PRIORITIES:
        raise ValueError("Unsupported task priority.")
    row = await add_project_memory(
        settings,
        user_id=user_id,
        project_id=project_id,
        memory_text=encode_entry(
            "task",
            {
                "title": clean_title,
                "status": clean_status,
                "priority": clean_priority,
                "notes": clean_notes,
            },
        ),
        source="v71",
        confidence=1.0,
    )
    return parse_entry(row) or {
        "kind": "task",
        "title": clean_title,
        "status": clean_status,
        "priority": clean_priority,
        "notes": clean_notes,
    }


async def update_task(
    settings: Any,
    *,
    user_id: str,
    project_id: str,
    item_id: str,
    title: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    entries = await list_entries(
        settings,
        user_id=user_id,
        project_id=project_id,
    )
    current = next(
        (
            item for item in entries
            if item.get("kind") == "task"
            and str(item.get("id") or "") == item_id
        ),
        None,
    )
    if not current:
        raise ValueError("Project Brain task not found.")

    next_title = _clean(
        current.get("title") if title is None else title,
        420,
    )
    next_status = str(
        current.get("status") if status is None else status
    ).strip().casefold()
    next_priority = str(
        current.get("priority") if priority is None else priority
    ).strip().casefold()
    next_notes = _clean(
        current.get("notes") if notes is None else notes,
        560,
    )

    if len(next_title) < 3:
        raise ValueError("Task title must contain at least 3 characters.")
    if next_status not in TASK_STATUSES:
        raise ValueError("Unsupported task status.")
    if next_priority not in TASK_PRIORITIES:
        raise ValueError("Unsupported task priority.")

    await delete_project_memory(
        settings,
        user_id=user_id,
        project_id=project_id,
        memory_id=item_id,
    )
    return await add_task(
        settings,
        user_id=user_id,
        project_id=project_id,
        title=next_title,
        status=next_status,
        priority=next_priority,
        notes=next_notes,
    )


async def delete_item(
    settings: Any,
    *,
    user_id: str,
    project_id: str,
    item_id: str,
) -> bool:
    entries = await list_entries(
        settings,
        user_id=user_id,
        project_id=project_id,
    )
    if not any(str(item.get("id") or "") == item_id for item in entries):
        return False
    return await delete_project_memory(
        settings,
        user_id=user_id,
        project_id=project_id,
        memory_id=item_id,
    )


def _task_summary(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {status: 0 for status in TASK_STATUSES}
    for task in tasks:
        status = str(task.get("status") or "pending")
        if status in counts:
            counts[status] += 1

    active = [task for task in tasks if task.get("status") != "done"]
    priority_rank = {"critical": 4, "high": 3, "normal": 2, "low": 1}
    status_rank = {"blocked": 4, "in_progress": 3, "pending": 2, "done": 1}
    active.sort(
        key=lambda item: (
            -priority_rank.get(str(item.get("priority") or "normal"), 2),
            -status_rank.get(str(item.get("status") or "pending"), 2),
            str(item.get("created_at") or ""),
        )
    )

    return {
        "counts": counts,
        "total": len(tasks),
        "open": len(active),
        "completion_pct": (
            round((counts["done"] / len(tasks)) * 100.0, 1)
            if tasks else 100.0
        ),
        "next_actions": active[:8],
    }


async def project_brain_snapshot(
    settings: Any,
    *,
    user_id: str,
    project_id: str,
) -> dict[str, Any]:
    project = await get_project(
        settings,
        user_id=user_id,
        project_id=project_id,
    )
    if not project:
        raise ValueError("Project not found.")

    entries = await list_entries(
        settings,
        user_id=user_id,
        project_id=project_id,
    )
    files = await list_project_files(
        settings,
        user_id=user_id,
        project_id=project_id,
        include_content=False,
        limit=500,
    )

    goal = next((item for item in entries if item.get("kind") == "goal"), None)
    last_work = next(
        (item for item in entries if item.get("kind") == "last_work"),
        None,
    )
    decisions = [item for item in entries if item.get("kind") == "decision"]
    tasks = [item for item in entries if item.get("kind") == "task"]
    repos = [item for item in entries if item.get("kind") == "repo"]

    languages = Counter(
        str(row.get("language") or "unknown")
        for row in files
        if str(row.get("language") or "").strip()
    )
    latest_file_update = max(
        (str(row.get("updated_at") or "") for row in files),
        default="",
    )

    return {
        "ok": True,
        "version": "v71",
        "project": project,
        "goal": goal,
        "last_work": last_work,
        "decisions": decisions,
        "tasks": tasks,
        "repos": repos,
        "task_summary": _task_summary(tasks),
        "files": {
            "count": len(files),
            "languages": dict(languages.most_common(12)),
            "latest_update": latest_file_update or None,
            "items": files[:80],
        },
        "persistence": {
            "backend": "existing-project-memories-and-project-kb",
            "new_database_migration_required": False,
        },
    }


def health_snapshot() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v71",
        "name": "Vasuki Project Brain 3.0",
        "features": [
            "persistent-project-goal",
            "persistent-project-decisions",
            "persistent-project-task-board",
            "persistent-last-work-checkpoint",
            "persistent-github-repo-links",
            "live-project-kb-file-summary",
            "next-action-prioritization",
            "existing-project-memory-storage",
        ],
        "storage": {
            "project_metadata": "projects",
            "brain_items": "project_memories source=v71",
            "files": "project_files_v9",
            "new_database_migration_required": False,
        },
        "old_project_data_preserved": True,
    }
