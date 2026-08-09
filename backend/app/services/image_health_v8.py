from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

_STATE: dict[str, dict[str, Any]] = defaultdict(
    lambda: {
        "attempts": 0,
        "successes": 0,
        "failures": 0,
        "ewma_latency_ms": None,
        "last_error": "",
        "blocked_until": 0.0,
        "quota_limited": False,
    }
)


def attempt(provider: str) -> None:
    _STATE[provider]["attempts"] += 1


def success(provider: str, latency_ms: float) -> None:
    item = _STATE[provider]
    item["successes"] += 1
    item["last_error"] = ""
    item["quota_limited"] = False
    old = item["ewma_latency_ms"]
    item["ewma_latency_ms"] = float(latency_ms) if old is None else (0.7 * old + 0.3 * float(latency_ms))


def failure(provider: str, error: Exception | str) -> None:
    item = _STATE[provider]
    item["failures"] += 1
    text = str(error)[:500]
    item["last_error"] = text
    low = text.casefold()
    now = time.monotonic()
    if "429" in low or "quota" in low or "rate-limit" in low or "rate limit" in low:
        item["blocked_until"] = max(item["blocked_until"], now + 900)
        item["quota_limited"] = True
    elif "401" in low or "403" in low or "payment" in low or "balance" in low:
        item["blocked_until"] = max(item["blocked_until"], now + 1800)
    elif "timeout" in low:
        item["blocked_until"] = max(item["blocked_until"], now + 90)
    elif item["failures"] >= 3:
        item["blocked_until"] = max(item["blocked_until"], now + 300)


def available(provider: str) -> bool:
    return time.monotonic() >= float(_STATE[provider]["blocked_until"] or 0.0)


def rank(providers: list[str]) -> list[str]:
    now = time.monotonic()

    def key(name: str):
        item = _STATE[name]
        blocked = float(item["blocked_until"] or 0.0) > now
        attempts = max(1, int(item["attempts"]))
        success_rate = float(item["successes"]) / attempts
        latency = item["ewma_latency_ms"]
        latency_value = float(latency) if latency is not None else 20000.0
        return (blocked, -success_rate, latency_value, int(item["failures"]))

    return sorted(providers, key=key)


def snapshot() -> dict[str, dict[str, Any]]:
    now = time.monotonic()
    result: dict[str, dict[str, Any]] = {}
    for name, item in _STATE.items():
        attempts = int(item["attempts"])
        result[name] = {
            "attempts": attempts,
            "successes": int(item["successes"]),
            "failures": int(item["failures"]),
            "success_rate": round(int(item["successes"]) / attempts, 4) if attempts else None,
            "ewma_latency_ms": round(float(item["ewma_latency_ms"]), 1) if item["ewma_latency_ms"] is not None else None,
            "last_error": str(item["last_error"] or ""),
            "cooldown_remaining_seconds": max(0, int(float(item["blocked_until"] or 0.0) - now)),
            "quota_limited": bool(item["quota_limited"]),
        }
    return result
