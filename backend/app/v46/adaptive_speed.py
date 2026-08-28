from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any


@dataclass
class ProviderSpeed:
    samples: int = 0
    successes: int = 0
    failures: int = 0
    ema_first_token_ms: float = 0.0


_LOCK = Lock()
_STATS: dict[tuple[str, str], ProviderSpeed] = {}


def _key(task_type: str, provider: str) -> tuple[str, str]:
    return (str(task_type or "general"), str(provider or ""))


def reset_speed_stats() -> None:
    with _LOCK:
        _STATS.clear()


def record_provider_success(provider: str, first_token_ms: float, task_type: str) -> None:
    if not provider or first_token_ms <= 0:
        return
    with _LOCK:
        row = _STATS.setdefault(_key(task_type, provider), ProviderSpeed())
        row.samples += 1
        row.successes += 1
        if row.ema_first_token_ms <= 0:
            row.ema_first_token_ms = float(first_token_ms)
        else:
            row.ema_first_token_ms = 0.35 * float(first_token_ms) + 0.65 * row.ema_first_token_ms


def record_provider_failure(provider: str, task_type: str) -> None:
    if not provider:
        return
    with _LOCK:
        row = _STATS.setdefault(_key(task_type, provider), ProviderSpeed())
        row.samples += 1
        row.failures += 1


def _score(row: ProviderSpeed) -> float:
    latency = row.ema_first_token_ms if row.ema_first_token_ms > 0 else 999999.0
    attempts = max(1, row.successes + row.failures)
    failure_rate = row.failures / attempts
    return latency * (1.0 + min(1.0, failure_rate) * 0.75)


def adaptive_provider_order(base_order: list[str], task_type: str, *, enabled: bool = True, min_samples: int = 2) -> list[str]:
    order = list(dict.fromkeys(base_order))
    if not enabled or len(order) < 2:
        return order

    if task_type == "code":
        head_size = min(2, len(order))
    elif task_type in {"research", "reasoning"}:
        return order
    else:
        head_size = min(3, len(order))

    head = order[:head_size]
    tail = order[head_size:]

    with _LOCK:
        rows = {name: _STATS.get(_key(task_type, name)) for name in head}
        if not all(
            row is not None
            and row.successes >= max(1, int(min_samples))
            and row.ema_first_token_ms > 0
            for row in rows.values()
        ):
            return order
        ranked = sorted(head, key=lambda name: (_score(rows[name]), head.index(name)))
    return ranked + tail


def first_token_timeout_seconds(task_type: str, *, large_request: bool, settings: Any) -> float:
    if large_request:
        return max(1.5, float(getattr(settings, "v46_large_first_token_timeout_seconds", 3.0)))
    if task_type == "code":
        return max(1.2, float(getattr(settings, "v46_code_first_token_timeout_seconds", 2.2)))
    return max(0.8, float(getattr(settings, "v46_simple_first_token_timeout_seconds", 1.25)))


def speed_snapshot() -> dict[str, Any]:
    with _LOCK:
        rows = []
        for (task_type, provider), row in sorted(_STATS.items()):
            attempts = row.successes + row.failures
            rows.append({
                "task_type": task_type,
                "provider": provider,
                "samples": row.samples,
                "successes": row.successes,
                "failures": row.failures,
                "first_token_ema_ms": round(row.ema_first_token_ms, 1) if row.ema_first_token_ms > 0 else None,
                "failure_rate": round(row.failures / max(1, attempts), 3),
            })
    return {"learning_scope": "process-memory", "resets_on_restart": True, "providers": rows}


def adaptive_speed_health(settings: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v46",
        "name": "Vasuki Adaptive Speed Router",
        "adaptive_speed_enabled": bool(getattr(settings, "v46_adaptive_speed_enabled", True)),
        "min_samples": int(getattr(settings, "v46_adaptive_min_samples", 2)),
        "simple_first_token_timeout_seconds": float(getattr(settings, "v46_simple_first_token_timeout_seconds", 1.25)),
        "code_first_token_timeout_seconds": float(getattr(settings, "v46_code_first_token_timeout_seconds", 2.2)),
        "large_first_token_timeout_seconds": float(getattr(settings, "v46_large_first_token_timeout_seconds", 3.0)),
        "provider_racing_enabled": False,
        "extra_provider_call_required": False,
        "latency_learning_persistent": False,
        "exclude_provider_supported": True,
        "cache_bypass_signature_supported": True,
        "v45_provider_diagnostics_preserved": True,
        "v44_zai_glm_preserved": True,
        "v43_instant_intent_preserved": True,
        "db_migration_required": False,
        "new_api_key_required": False,
        "new_python_dependency_required": False,
        "performance": speed_snapshot(),
    }
