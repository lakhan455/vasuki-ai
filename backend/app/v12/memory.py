\
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


_SOURCE_PRIORITY = {
    "explicit_user": 100,
    "user": 95,
    "project": 80,
    "imported": 65,
    "inferred": 50,
    "assistant": 30,
}


def _tokens(text: str) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"\w+", text or "", flags=re.UNICODE)
        if len(token) > 1
    }


def _similarity(a: str, b: str) -> float:
    ta = _tokens(a)
    tb = _tokens(b)

    if not ta or not tb:
        return 0.0

    return len(ta & tb) / max(1, min(len(ta), len(tb)))


def _timestamp(row: dict[str, Any]) -> float:
    raw = str(
        row.get("valid_from")
        or row.get("updated_at")
        or row.get("created_at")
        or ""
    )

    if not raw:
        return 0.0

    try:
        value = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(value).timestamp()
    except Exception:
        return 0.0


def _priority(row: dict[str, Any]) -> tuple[float, int]:
    source = str(row.get("source") or "").strip().lower()
    return (
        _timestamp(row),
        _SOURCE_PRIORITY.get(source, 40),
    )


def resolve_conflicts_v12(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    active = [
        dict(row)
        for row in rows
        if str(row.get("status") or "active") == "active"
    ]

    active.sort(key=_priority, reverse=True)

    chosen: list[dict[str, Any]] = []

    for row in active:
        row_key = str(
            row.get("key_norm")
            or row.get("key")
            or ""
        )

        conflict_with = None

        for accepted in chosen:
            accepted_key = str(
                accepted.get("key_norm")
                or accepted.get("key")
                or ""
            )

            similarity = _similarity(row_key, accepted_key)

            if similarity >= 0.72:
                conflict_with = accepted
                break

        if conflict_with is None:
            row["v12_conflict_resolution"] = {
                "selected": True,
                "reason": "newest-highest-priority",
            }
            chosen.append(row)

    return chosen
