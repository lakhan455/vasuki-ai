from __future__ import annotations

import re
import time
from collections import deque
from threading import Lock
from typing import Any

from app.v11 import store


_LOCK = Lock()
_EVENTS: deque[dict[str, Any]] = deque(maxlen=300)
_SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b(?:bearer|apikey|api[_ -]?key|secret|token|password)\s*[:=]\s*\S+"
    ),
)


def _safe(value: object, limit: int = 700) -> str:
    text = str(value or "")[:limit]
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted]", text)
    return text


def record_degraded(
    component: str,
    operation: str,
    error: object,
    *,
    severity: str = "warning",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "time": int(time.time()),
        "component": _safe(component, 120),
        "operation": _safe(operation, 160),
        "severity": _safe(severity, 30),
        "error": _safe(error),
        "metadata": {
            _safe(k, 100): _safe(v, 500)
            for k, v in (metadata or {}).items()
        },
    }
    with _LOCK:
        _EVENTS.append(row)
    return row


def snapshot(limit: int = 50) -> dict[str, Any]:
    with _LOCK:
        rows = list(_EVENTS)[-max(1, min(200, int(limit))):]
    by_component: dict[str, int] = {}
    for row in rows:
        key = str(row.get("component") or "unknown")
        by_component[key] = by_component.get(key, 0) + 1
    return {
        "event_count": len(rows),
        "by_component": by_component,
        "recent": rows,
    }


async def persist_checkpoint(
    settings: Any,
    component: str,
    payload: dict[str, Any],
) -> bool:
    if not bool(getattr(settings, "v50_persist_runtime_state", True)):
        return False
    if not store.configured(settings):
        return False
    try:
        await store.request(
            settings,
            "POST",
            "v11_provider_quality",
            json_body={
                "task_type": "system",
                "provider": "v50-runtime",
                "signal_type": f"v50_checkpoint_{component}"[:120],
                "signal_value": 1.0,
                "metadata": payload,
            },
            timeout=2.0,
        )
        return True
    except Exception as exc:
        record_degraded("runtime_state", f"persist:{component}", exc, severity="info")
        return False


async def restore_checkpoint(
    settings: Any,
    component: str,
) -> dict[str, Any] | None:
    if not bool(getattr(settings, "v50_persist_runtime_state", True)):
        return None
    if not store.configured(settings):
        return None
    try:
        rows = await store.request(
            settings,
            "GET",
            "v11_provider_quality",
            params={
                "task_type": "eq.system",
                "provider": "eq.v50-runtime",
                "signal_type": f"eq.v50_checkpoint_{component}"[:123],
                "select": "metadata,created_at",
                "order": "created_at.desc",
                "limit": "1",
            },
            timeout=2.0,
        ) or []
        if isinstance(rows, list) and rows:
            metadata = rows[0].get("metadata")
            if isinstance(metadata, dict):
                return metadata
    except Exception as exc:
        record_degraded("runtime_state", f"restore:{component}", exc, severity="info")
    return None
