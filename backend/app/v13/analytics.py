from __future__ import annotations

from typing import Any


def provider_health_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    configured = {
        name: data
        for name, data in (snapshot or {}).items()
        if isinstance(data, dict) and bool(data.get("configured"))
    }
    tasks = ("simple", "general", "code", "reasoning", "research")
    best_by_task: dict[str, dict[str, Any]] = {}
    degraded: list[dict[str, Any]] = []

    for task in tasks:
        rows: list[tuple[float, str, dict[str, Any]]] = []
        for provider, data in configured.items():
            metrics = (data.get("tasks") or {}).get(task) or {}
            if not isinstance(metrics, dict):
                continue
            score = float(metrics.get("score") or 0.0)
            rows.append((score, provider, metrics))
            success = float(metrics.get("success_rate") or 0.0)
            speed = float(metrics.get("speed") or 0.0)
            if success < 0.5 or speed < 0.25:
                degraded.append(
                    {
                        "provider": provider,
                        "task": task,
                        "score": round(score, 4),
                        "success_rate": round(success, 4),
                        "speed": round(speed, 4),
                    }
                )

        if rows:
            rows.sort(key=lambda row: row[0], reverse=True)
            score, provider, metrics = rows[0]
            best_by_task[task] = {
                "provider": provider,
                "score": round(score, 4),
                "success_rate": round(float(metrics.get("success_rate") or 0.0), 4),
                "speed": round(float(metrics.get("speed") or 0.0), 4),
            }

    unique_degraded = {
        (row["provider"], row["task"]): row
        for row in degraded
    }

    return {
        "configured_providers": sorted(configured),
        "configured_count": len(configured),
        "best_by_task": best_by_task,
        "degraded": list(unique_degraded.values()),
        "degraded_count": len(unique_degraded),
    }
