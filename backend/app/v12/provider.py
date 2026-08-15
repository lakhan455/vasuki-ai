\
from __future__ import annotations

from typing import Any

from app.services.quality_v9 import metrics as runtime_metrics
from app.v11.capabilities import PROVIDER_FIELDS
from app.v11.quality import learned_quality


def provider_score_v12(provider: str, task_type: str = "general") -> float:
    task = str(task_type or "general").strip().lower()
    runtime = runtime_metrics(provider, task)
    feedback_quality = float(runtime.get("quality", 0.72))
    reliability = float(runtime.get("reliability", 1.0))
    speed = float(runtime.get("speed", 0.78))
    benchmark = float(learned_quality(provider, task))
    availability = 1.0 if reliability > 0.0 else 0.0

    score = (
        feedback_quality * 0.45
        + benchmark * 0.20
        + reliability * 0.15
        + speed * 0.10
        + availability * 0.10
    )
    return round(max(0.0, min(1.0, score)), 6)


def rank_for_task_v12(
    names: list[str],
    task_type: str = "general",
) -> list[str]:
    ranked = [
        (
            provider_score_v12(name, task_type) - index * 0.003,
            name,
        )
        for index, name in enumerate(names)
    ]
    ranked.sort(reverse=True)
    return [name for _, name in ranked]


def provider_snapshot_v12(settings) -> dict[str, Any]:
    tasks = ["simple", "general", "code", "reasoning", "research"]
    output: dict[str, Any] = {}

    for provider, field in PROVIDER_FIELDS.items():
        configured = bool(str(getattr(settings, field, "") or "").strip())
        output[provider] = {
            "configured": configured,
            "tasks": {},
        }

        for task in tasks:
            runtime = runtime_metrics(provider, task)
            output[provider]["tasks"][task] = {
                "score": provider_score_v12(provider, task),
                "feedback_quality": round(float(runtime.get("quality", 0.0)), 4),
                "benchmark_quality": round(float(learned_quality(provider, task)), 4),
                "success_rate": round(float(runtime.get("reliability", 0.0)), 4),
                "speed": round(float(runtime.get("speed", 0.0)), 4),
            }

    return output
