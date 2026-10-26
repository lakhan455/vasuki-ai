from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any


_LOCK = threading.Lock()
_LIVE_SEARCH = deque(maxlen=240)
_QUALITY = deque(maxlen=240)
_TRUTH_GUARD = deque(maxlen=240)


def observe_live_search(
    *,
    ok: bool,
    source_count: int,
    duration_ms: float,
    current_required: bool,
    error: str = "",
) -> None:
    row = {
        "at": time.time(),
        "ok": bool(ok),
        "source_count": max(0, int(source_count)),
        "duration_ms": max(0.0, float(duration_ms)),
        "current_required": bool(current_required),
        "error": str(error or "")[:180],
    }
    with _LOCK:
        _LIVE_SEARCH.append(row)


def observe_answer_quality(
    *,
    score: float,
    current_required: bool,
    source_count: int,
    provider: str = "",
) -> None:
    row = {
        "at": time.time(),
        "score": max(0.0, min(100.0, float(score))),
        "current_required": bool(current_required),
        "source_count": max(0, int(source_count)),
        "provider": str(provider or "")[:80],
    }
    with _LOCK:
        _QUALITY.append(row)


def observe_truth_guard(reason: str) -> None:
    with _LOCK:
        _TRUTH_GUARD.append(
            {
                "at": time.time(),
                "reason": str(reason or "unknown")[:160],
            }
        )


def _pct(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


def reliability_snapshot() -> dict[str, Any]:
    with _LOCK:
        searches = list(_LIVE_SEARCH)
        quality = list(_QUALITY)
        guards = list(_TRUTH_GUARD)

    current_searches = [row for row in searches if row["current_required"]]
    successful = [row for row in current_searches if row["ok"] and row["source_count"] > 0]
    search_availability = (
        100.0 * len(successful) / len(current_searches)
        if current_searches
        else 100.0
    )

    source_rich = [row for row in successful if row["source_count"] >= 2]
    grounding_rate = (
        100.0 * len(source_rich) / len(successful)
        if successful
        else (100.0 if not current_searches else 0.0)
    )

    average_quality = (
        sum(float(row["score"]) for row in quality) / len(quality)
        if quality
        else 100.0
    )
    current_quality_rows = [row for row in quality if row["current_required"]]
    current_quality = (
        sum(float(row["score"]) for row in current_quality_rows)
        / len(current_quality_rows)
        if current_quality_rows
        else average_quality
    )

    composite = (
        search_availability * 0.38
        + grounding_rate * 0.22
        + current_quality * 0.40
    )

    if composite >= 92:
        state = "healthy"
    elif composite >= 78:
        state = "watch"
    else:
        state = "degraded"

    latest_failures = [
        {
            "error": row["error"] or "no-live-evidence",
            "source_count": row["source_count"],
            "duration_ms": round(row["duration_ms"]),
        }
        for row in searches
        if not row["ok"] or row["source_count"] <= 0
    ][-8:]

    return {
        "state": state,
        "score": _pct(composite),
        "samples": {
            "live_search": len(searches),
            "current_search": len(current_searches),
            "answer_quality": len(quality),
            "truth_guard": len(guards),
        },
        "metrics": {
            "current_search_availability_pct": _pct(search_availability),
            "multi_source_grounding_pct": _pct(grounding_rate),
            "average_answer_quality": _pct(average_quality),
            "current_fact_answer_quality": _pct(current_quality),
            "truth_guard_blocks": len(guards),
        },
        "recent_search_failures": latest_failures,
        "privacy": {
            "stores_prompts": False,
            "stores_answers": False,
            "stores_user_ids": False,
            "in_memory_only": True,
        },
    }


def health_snapshot() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v67",
        "name": "Vasuki Reliability Scorecard",
        "reliability": reliability_snapshot(),
        "new_database_migration_required": False,
        "stores_user_content": False,
    }
