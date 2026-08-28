from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass
from threading import Lock
from typing import Any

from app.v11 import store


@dataclass
class ProviderReliability:
    samples: int = 0
    successes: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    ema_first_token_ms: float = 0.0
    ema_total_latency_ms: float = 0.0
    last_error: str = ""
    circuit_open_until: float = 0.0


_LOCK = Lock()
_STATS: dict[tuple[str, str], ProviderReliability] = {}
_PERSIST_TASKS: set[asyncio.Task] = set()


def _key(task_type: str, provider: str) -> tuple[str, str]:
    return (str(task_type or "general").strip().lower(), str(provider or "").strip())


def _ema(previous: float, value: float, alpha: float = 0.30) -> float:
    if value <= 0:
        return previous
    return float(value) if previous <= 0 else (alpha * float(value)) + ((1.0 - alpha) * previous)


def reset_reliability_stats() -> None:
    with _LOCK:
        _STATS.clear()


def _failure_kind(error: object) -> str:
    text = str(error or "").casefold()
    if any(token in text for token in ("429", "quota", "rate limit", "too many requests")):
        return "quota"
    if any(token in text for token in ("401", "402", "403", "unauthorized", "payment required")):
        return "auth"
    if any(token in text for token in ("timeout", "timed out")):
        return "timeout"
    if any(token in text for token in ("502", "503", "504", "connection", "temporarily unavailable")):
        return "transient"
    return "unknown"


def observe_provider_success(
    provider: str,
    task_type: str,
    *,
    first_token_ms: float,
    total_latency_ms: float,
) -> ProviderReliability:
    if not provider:
        return ProviderReliability()
    with _LOCK:
        row = _STATS.setdefault(_key(task_type, provider), ProviderReliability())
        row.samples += 1
        row.successes += 1
        row.consecutive_failures = 0
        row.last_error = ""
        row.circuit_open_until = 0.0
        row.ema_first_token_ms = _ema(row.ema_first_token_ms, float(first_token_ms or 0))
        row.ema_total_latency_ms = _ema(row.ema_total_latency_ms, float(total_latency_ms or 0))
        return ProviderReliability(**asdict(row))


def observe_provider_failure(
    provider: str,
    task_type: str,
    error: object,
    settings: Any,
) -> ProviderReliability:
    if not provider:
        return ProviderReliability()
    kind = _failure_kind(error)
    now = time.monotonic()
    with _LOCK:
        row = _STATS.setdefault(_key(task_type, provider), ProviderReliability())
        row.samples += 1
        row.failures += 1
        row.consecutive_failures += 1
        row.last_error = str(error or "")[:320]

        threshold = max(1, int(getattr(settings, "v47_circuit_failure_threshold", 2)))
        base = max(5.0, float(getattr(settings, "v47_circuit_base_cooldown_seconds", 45.0)))
        cap = max(base, float(getattr(settings, "v47_circuit_max_cooldown_seconds", 900.0)))

        if kind == "auth":
            cooldown = min(cap, max(base, 900.0))
        elif kind == "quota":
            cooldown = min(cap, max(base, 600.0))
        elif row.consecutive_failures >= threshold:
            exponent = min(6, row.consecutive_failures - threshold)
            cooldown = min(cap, base * (2 ** exponent))
        elif kind == "timeout":
            cooldown = min(cap, max(15.0, base * 0.5))
        else:
            cooldown = 0.0

        if cooldown > 0:
            row.circuit_open_until = max(row.circuit_open_until, now + cooldown)
        return ProviderReliability(**asdict(row))


def provider_available(provider: str, task_type: str) -> bool:
    now = time.monotonic()
    with _LOCK:
        row = _STATS.get(_key(task_type, provider))
        return row is None or row.circuit_open_until <= now


def _runtime_score(row: ProviderReliability | None, task_type: str) -> float:
    if row is None or row.samples <= 0:
        return 1.0
    attempts = max(1, row.successes + row.failures)
    success_rate = row.successes / attempts
    target_first = 1300.0 if task_type in {"simple", "general"} else 2200.0
    if task_type in {"research", "reasoning"}:
        target_first = 3000.0
    latency = row.ema_first_token_ms or target_first
    speed_ratio = min(3.0, latency / target_first)
    failure_penalty = (1.0 - success_rate) * 2.6 + min(3, row.consecutive_failures) * 0.45
    return round(speed_ratio * 0.72 + failure_penalty + 0.28, 6)


def _health_score(row: ProviderReliability | None, task_type: str) -> float:
    if row is None or row.samples <= 0:
        return 0.82
    attempts = max(1, row.successes + row.failures)
    # Bayesian prior avoids showing a misleading 100% after a single success.
    success_health = (row.successes + 4.1) / (attempts + 5.0)
    target_first = 1300.0 if task_type in {"simple", "general"} else 2200.0
    if task_type in {"research", "reasoning"}:
        target_first = 3000.0
    latency = row.ema_first_token_ms or target_first
    speed_health = max(0.0, min(1.0, target_first / max(1.0, latency)))
    consecutive_penalty = min(0.35, row.consecutive_failures * 0.10)
    return max(0.0, min(1.0, success_health * 0.72 + speed_health * 0.28 - consecutive_penalty))


def reliability_score(provider: str, task_type: str) -> float:
    with _LOCK:
        row = _STATS.get(_key(task_type, provider))
        score = _health_score(row, task_type)
    return round(score, 4)


def adaptive_reliability_order(
    names: list[str],
    task_type: str,
    tier: str,
    settings: Any,
) -> list[str]:
    order = list(dict.fromkeys(names))
    if not bool(getattr(settings, "v47_reliability_router_enabled", True)) or len(order) < 2:
        return order

    # Keep the upstream quality rank as the anchor. V47 only optimizes inside
    # a small quality band, so a historically fast weak provider cannot jump
    # ahead of every high-quality candidate.
    if task_type == "code":
        band_size = min(3, len(order))
    elif task_type in {"research", "reasoning"}:
        band_size = min(2, len(order))
    else:
        band_size = min(4 if tier == "fast" else 3, len(order))

    head = order[:band_size]
    tail = order[band_size:]
    min_samples = max(1, int(getattr(settings, "v47_adaptive_min_samples", 2)))
    now = time.monotonic()

    with _LOCK:
        rows = {name: _STATS.get(_key(task_type, name)) for name in head}
        healthy = [
            name for name in head
            if rows[name] is None or rows[name].circuit_open_until <= now
        ]
        cooled = [name for name in head if name not in healthy]

        # If every provider in the quality band is open, preserve the original
        # order and let the existing V18 last-resort recovery path decide.
        if not healthy:
            return order

        def key(name: str) -> tuple[float, int]:
            row = rows[name]
            if row is None or row.samples < min_samples:
                # Unknown providers stay close to their quality-ranked position
                # until enough real traffic has been observed.
                return (1.0 + head.index(name) * 0.025, head.index(name))
            return (_runtime_score(row, task_type), head.index(name))

        ranked = sorted(healthy, key=key)

    return ranked + cooled + tail


def first_token_timeout_for_provider(
    provider: str,
    task_type: str,
    *,
    tier: str,
    settings: Any,
    recovery_mode: bool = False,
) -> float:
    if tier == "strong":
        base = float(getattr(settings, "v46_large_first_token_timeout_seconds", 3.0))
        ceiling = float(getattr(settings, "v47_large_first_token_timeout_max_seconds", 7.0))
    elif task_type == "code":
        base = float(getattr(settings, "v46_code_first_token_timeout_seconds", 2.2))
        ceiling = float(getattr(settings, "v47_code_first_token_timeout_max_seconds", 5.5))
    else:
        base = float(getattr(settings, "v46_simple_first_token_timeout_seconds", 1.25))
        ceiling = float(getattr(settings, "v47_simple_first_token_timeout_max_seconds", 3.5))

    floor = max(0.8, float(getattr(settings, "v47_first_token_timeout_floor_seconds", 1.0)))
    min_samples = max(1, int(getattr(settings, "v47_adaptive_min_samples", 2)))

    with _LOCK:
        row = _STATS.get(_key(task_type, provider))
        learned_ms = row.ema_first_token_ms if row and row.samples >= min_samples else 0.0

    timeout = max(floor, base)
    if learned_ms > 0:
        timeout = max(floor, min(ceiling, learned_ms / 1000.0 * 1.9 + 0.35))

    if recovery_mode:
        timeout = max(timeout, float(getattr(settings, "v18_chat_recovery_first_token_seconds", 4.5)))
    return round(min(max(floor, timeout), max(floor, ceiling if not recovery_mode else max(ceiling, timeout))), 3)


def reliability_snapshot() -> dict[str, Any]:
    now = time.monotonic()
    with _LOCK:
        rows: list[dict[str, Any]] = []
        for (task_type, provider), row in sorted(_STATS.items()):
            attempts = max(1, row.successes + row.failures)
            rows.append({
                "task_type": task_type,
                "provider": provider,
                "samples": row.samples,
                "successes": row.successes,
                "failures": row.failures,
                "success_rate": round(row.successes / attempts, 4),
                "consecutive_failures": row.consecutive_failures,
                "first_token_ema_ms": round(row.ema_first_token_ms, 1) if row.ema_first_token_ms > 0 else None,
                "total_latency_ema_ms": round(row.ema_total_latency_ms, 1) if row.ema_total_latency_ms > 0 else None,
                "reliability_score": round(_health_score(row, task_type), 4),
                "circuit_open": row.circuit_open_until > now,
                "cooldown_remaining_seconds": max(0, round(row.circuit_open_until - now)),
                "last_error": row.last_error,
            })
    return {
        "learning_scope": "process-memory + Supabase restore",
        "resets_on_restart": False,
        "providers": rows,
    }


def _schedule(coro) -> None:
    try:
        task = asyncio.create_task(coro)
    except RuntimeError:
        return
    _PERSIST_TASKS.add(task)
    task.add_done_callback(_PERSIST_TASKS.discard)


async def _persist_runtime_signal(
    settings: Any,
    *,
    provider: str,
    task_type: str,
    success: bool,
    first_token_ms: float | None = None,
    total_latency_ms: float | None = None,
    error: str = "",
) -> None:
    if not bool(getattr(settings, "v47_persistent_learning_enabled", True)):
        return
    if not store.configured(settings):
        return
    metadata = {
        "success": bool(success),
        "first_token_ms": float(first_token_ms or 0.0),
        "total_latency_ms": float(total_latency_ms or 0.0),
        "error_kind": _failure_kind(error) if not success else "",
        "error": str(error or "")[:300],
        "router_version": "v47",
    }
    try:
        await store.request(
            settings,
            "POST",
            "v11_provider_quality",
            json_body={
                "task_type": str(task_type or "general"),
                "provider": str(provider or ""),
                "signal_type": "v47_runtime_success" if success else "v47_runtime_failure",
                "signal_value": 1.0 if success else 0.0,
                "metadata": metadata,
            },
            timeout=max(0.4, float(getattr(settings, "v47_persist_timeout_seconds", 1.2))),
        )
    except Exception:
        pass


def persist_success_later(
    settings: Any,
    provider: str,
    task_type: str,
    *,
    first_token_ms: float,
    total_latency_ms: float,
) -> None:
    if not bool(getattr(settings, "v47_persistent_learning_enabled", True)):
        return
    every = max(1, int(getattr(settings, "v47_persist_every_n_successes", 3)))
    with _LOCK:
        row = _STATS.get(_key(task_type, provider))
        successes = row.successes if row else 0
    if successes % every != 0:
        return
    _schedule(_persist_runtime_signal(
        settings,
        provider=provider,
        task_type=task_type,
        success=True,
        first_token_ms=first_token_ms,
        total_latency_ms=total_latency_ms,
    ))


def persist_failure_later(settings: Any, provider: str, task_type: str, error: object) -> None:
    if not bool(getattr(settings, "v47_persistent_learning_enabled", True)):
        return
    _schedule(_persist_runtime_signal(
        settings,
        provider=provider,
        task_type=task_type,
        success=False,
        error=str(error or "")[:300],
    ))


async def load_persisted_reliability(settings: Any, limit: int = 2500) -> int:
    if not bool(getattr(settings, "v47_persistent_learning_enabled", True)):
        return 0
    if not store.configured(settings):
        return 0
    try:
        rows = await store.request(
            settings,
            "GET",
            "v11_provider_quality",
            params={
                "select": "task_type,provider,signal_type,signal_value,metadata,created_at",
                "signal_type": "like.v47_runtime_*",
                "order": "created_at.desc",
                "limit": str(max(1, min(5000, int(limit)))),
            },
            timeout=max(1.0, float(getattr(settings, "v47_restore_timeout_seconds", 4.0))),
        ) or []
    except Exception:
        return 0

    loaded = 0
    # Replay oldest -> newest so EMA values remain meaningful.
    for item in reversed(rows):
        provider = str(item.get("provider") or "").strip()
        task_type = str(item.get("task_type") or "general").strip().lower()
        signal = str(item.get("signal_type") or "")
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        if not provider or not signal.startswith("v47_runtime_"):
            continue
        with _LOCK:
            row = _STATS.setdefault(_key(task_type, provider), ProviderReliability())
            row.samples += 1
            if signal == "v47_runtime_success":
                row.successes += 1
                row.consecutive_failures = 0
                row.ema_first_token_ms = _ema(row.ema_first_token_ms, float(metadata.get("first_token_ms") or 0.0))
                row.ema_total_latency_ms = _ema(row.ema_total_latency_ms, float(metadata.get("total_latency_ms") or 0.0))
                row.last_error = ""
            elif signal == "v47_runtime_failure":
                row.failures += 1
                row.consecutive_failures += 1
                row.last_error = str(metadata.get("error") or "")[:320]
            else:
                continue
        loaded += 1
    return loaded


async def flush_persistence(timeout_seconds: float = 1.5) -> None:
    tasks = [task for task in list(_PERSIST_TASKS) if not task.done()]
    if not tasks:
        return
    try:
        await asyncio.wait(tasks, timeout=max(0.1, timeout_seconds))
    except Exception:
        pass


def v47_health(settings: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v47",
        "name": "Vasuki Self-Healing Persistent Reliability Router",
        "features": [
            "production-chat-v7-integration",
            "persistent-runtime-provider-learning",
            "task-aware-reliability-ranking",
            "exponential-circuit-breaker",
            "provider-specific-first-token-timeout",
            "quality-band-preservation",
            "restart-learning-restore",
            "provider-model-latency-diagnostics",
        ],
        "reliability_router_enabled": bool(getattr(settings, "v47_reliability_router_enabled", True)),
        "persistent_learning_enabled": bool(getattr(settings, "v47_persistent_learning_enabled", True)),
        "adaptive_min_samples": int(getattr(settings, "v47_adaptive_min_samples", 2)),
        "circuit_failure_threshold": int(getattr(settings, "v47_circuit_failure_threshold", 2)),
        "circuit_base_cooldown_seconds": float(getattr(settings, "v47_circuit_base_cooldown_seconds", 45.0)),
        "circuit_max_cooldown_seconds": float(getattr(settings, "v47_circuit_max_cooldown_seconds", 900.0)),
        "db_migration_required": False,
        "reuses_v11_provider_quality_table": True,
        "new_api_key_required": False,
        "new_python_dependency_required": False,
        "provider_racing_enabled": False,
        "extra_provider_call_required": False,
        "v46_preserved": True,
        "v45_diagnostics_preserved": True,
        "runtime": reliability_snapshot(),
    }
