from __future__ import annotations

import re
from typing import Any


def classify_task_status(item: dict[str, Any]) -> str:
    explicit = str(item.get("status") or "").strip().casefold()
    if explicit in {"done", "complete", "completed", "finished"}:
        return "done"
    if explicit in {"blocked", "stuck", "waiting"}:
        return "blocked"
    if explicit in {"testing", "test", "qa", "review"}:
        return "testing"
    if explicit in {"pending", "todo", "open", "planned"}:
        return "pending"

    text = " ".join(
        str(item.get(key) or "")
        for key in ("title", "description", "notes")
    ).casefold()
    if re.search(r"\b(?:blocked|stuck|waiting for|cannot proceed)\b", text):
        return "blocked"
    if re.search(r"\b(?:test|testing|qa|verify|verification|review)\b", text):
        return "testing"
    if re.search(r"\b(?:done|completed|finished|fixed|resolved|merged)\b", text):
        return "done"
    return "pending"


def _priority(item: dict[str, Any], status: str) -> int:
    text = " ".join(
        str(item.get(key) or "")
        for key in ("title", "description", "notes", "priority")
    ).casefold()
    if status == "blocked":
        return 100
    if re.search(r"\b(?:critical|urgent|p0|production|security|outage)\b", text):
        return 90
    if status == "testing":
        return 70
    if re.search(r"\b(?:high|p1|important)\b", text):
        return 60
    return 40


def project_snapshot(items: list[dict[str, Any]]) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    counts = {"done": 0, "testing": 0, "pending": 0, "blocked": 0}

    for index, item in enumerate(items):
        status = classify_task_status(item)
        counts[status] += 1
        normalized.append(
            {
                **item,
                "_index": index,
                "status": status,
                "priority_score": _priority(item, status),
            }
        )

    total = len(normalized)
    completion_pct = round((counts["done"] / total) * 100.0, 1) if total else 100.0
    active = [row for row in normalized if row["status"] != "done"]
    active.sort(key=lambda row: (-int(row["priority_score"]), int(row["_index"])))

    next_actions = [
        {
            "title": str(row.get("title") or row.get("description") or f"Task {row['_index'] + 1}")[:300],
            "status": row["status"],
            "priority_score": row["priority_score"],
        }
        for row in active[:10]
    ]
    blocked = [row for row in normalized if row["status"] == "blocked"]

    return {
        "total": total,
        "counts": counts,
        "completion_pct": completion_pct,
        "blocked_count": len(blocked),
        "next_actions": next_actions,
        "items": normalized,
    }
