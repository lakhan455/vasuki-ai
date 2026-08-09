from __future__ import annotations
from collections import defaultdict, deque
from threading import Lock
from typing import Any
from app.services.telemetry_v7 import snapshot as health_snapshot

_LOCK = Lock()
_FEEDBACK: dict[str, dict[str, deque[float]]] = defaultdict(
    lambda: defaultdict(lambda: deque(maxlen=120))
)
_WEIGHTS = {
    "simple": (0.36, 0.24, 0.40),
    "general": (0.50, 0.25, 0.25),
    "code": (0.62, 0.20, 0.18),
    "reasoning": (0.66, 0.20, 0.14),
    "research": (0.68, 0.22, 0.10),
}

def _quality(provider: str, task: str) -> float:
    with _LOCK:
        rows = list(_FEEDBACK.get(task, {}).get(provider, ()))
        if not rows:
            rows = list(_FEEDBACK.get("general", {}).get(provider, ()))
    return sum(rows) / len(rows) if rows else 0.72

def metrics(provider: str, task: str) -> dict[str, float]:
    h = health_snapshot().get(provider, {})
    reliability = float(h.get("success_rate", 1.0))
    latency = h.get("ewma_latency_ms")
    speed = 0.78 if latency is None else max(0.0, min(1.0, 1.0 - float(latency) / 18000.0))
    return {"quality": _quality(provider, task), "reliability": reliability, "speed": speed}

def provider_score(provider: str, task: str = "general") -> float:
    task = task if task in _WEIGHTS else "general"
    q, r, s = _WEIGHTS[task]
    m = metrics(provider, task)
    return round(m["quality"] * q + m["reliability"] * r + m["speed"] * s, 6)

def rank_for_task(names: list[str], task: str = "general") -> list[str]:
    rows = [(provider_score(name, task) - i * 0.008, name) for i, name in enumerate(names)]
    rows.sort(reverse=True)
    return [name for _, name in rows]

def observe_feedback(provider: str | None, rating: str, *, task_type: str | None = None, category: str | None = None):
    name = str(provider or "").replace("cache:", "").strip()
    if not name:
        return
    task = str(task_type or "").strip().lower()
    cat = str(category or "").strip().lower()
    if not task:
        task = "code" if "code" in cat else ("research" if "outdated" in cat else "general")
    value = 1.0 if str(rating).lower().startswith("u") else 0.0
    with _LOCK:
        _FEEDBACK[task][name].append(value)

def quality_snapshot() -> dict[str, Any]:
    providers = sorted(health_snapshot().keys())
    tasks = ["simple", "general", "code", "reasoning", "research"]
    return {
        p: {t: {"score": provider_score(p, t), **metrics(p, t)} for t in tasks}
        for p in providers
    }

def operational_eval_score() -> dict[str, Any]:
    h = health_snapshot()
    if not h:
        reliability, speed = 75, 75
    else:
        rates = [float(v.get("success_rate", 1.0)) for v in h.values()]
        lats = [float(v["ewma_latency_ms"]) for v in h.values() if v.get("ewma_latency_ms") is not None]
        reliability = round(100 * sum(rates) / max(1, len(rates)))
        avg = sum(lats) / max(1, len(lats)) if lats else 4500.0
        speed = round(max(0.0, min(100.0, 100.0 - avg / 180.0)))
    return {
        "Accuracy": None,
        "Coding": None,
        "Research": None,
        "Vision": None,
        "Speed": speed,
        "Reliability": reliability,
        "note": "Accuracy/Coding/Research/Vision come from benchmark runs; runtime health supplies Speed/Reliability.",
    }
