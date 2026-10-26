from __future__ import annotations

from typing import Any


def _enabled(settings: Any) -> bool:
    return bool(getattr(settings, "v51_speed_lane_enabled", True))


def context_policy(decision: Any, settings: Any) -> tuple[int, int]:
    hard_limit = max(8000, int(getattr(settings, "max_context_chars", 45000)))
    if not _enabled(settings):
        return hard_limit, 12

    tier = str(getattr(decision, "tier", "balanced") or "balanced")
    task_type = str(getattr(decision, "task_type", "general") or "general")

    if tier == "fast":
        budget = int(getattr(settings, "v51_fast_context_chars", 16000))
        preserve_last = 8
    elif task_type in {"code", "research", "reasoning"} or tier == "strong":
        budget = int(getattr(settings, "v51_strong_context_chars", 42000))
        preserve_last = 12
    else:
        budget = int(getattr(settings, "v51_general_context_chars", 28000))
        preserve_last = 10

    return max(8000, min(hard_limit, budget)), preserve_last


def provider_attempt_budget(
    decision: Any,
    settings: Any,
    provider: str = "auto",
) -> int:
    hard_limit = max(1, min(7, int(getattr(settings, "max_provider_attempts", 7))))
    if provider != "auto":
        return 1
    if not _enabled(settings):
        return hard_limit

    tier = str(getattr(decision, "tier", "balanced") or "balanced")
    task_type = str(getattr(decision, "task_type", "general") or "general")

    if tier == "fast":
        desired = int(getattr(settings, "v51_fast_provider_attempts", 3))
    elif task_type in {"code", "research", "reasoning"} or tier == "strong":
        desired = int(getattr(settings, "v51_strong_provider_attempts", 5))
    else:
        desired = int(getattr(settings, "v51_general_provider_attempts", 4))

    return max(1, min(hard_limit, desired))


def gemini_timeout_seconds(decision: Any, settings: Any) -> float:
    if not _enabled(settings):
        return float(getattr(settings, "large_provider_timeout_seconds", 45))

    tier = str(getattr(decision, "tier", "balanced") or "balanced")
    task_type = str(getattr(decision, "task_type", "general") or "general")

    if tier == "fast":
        return max(3.0, float(getattr(settings, "v51_gemini_fast_timeout_seconds", 7.5)))
    if task_type in {"code", "research", "reasoning"} or tier == "strong":
        return max(6.0, float(getattr(settings, "v51_gemini_strong_timeout_seconds", 18.0)))
    return max(4.0, float(getattr(settings, "v51_gemini_general_timeout_seconds", 11.0)))


def should_lookup_shared_knowledge(
    *,
    direct_fact: bool,
    current_required: bool,
    authoritative_snapshot_candidate: bool,
    settings: Any,
) -> bool:
    if not _enabled(settings):
        return True
    if not bool(getattr(settings, "v51_skip_unneeded_shared_lookup", True)):
        return True
    if authoritative_snapshot_candidate:
        return True
    if current_required:
        return False
    return bool(direct_fact)


def memory_context_timeout_seconds(settings: Any) -> float:
    if not _enabled(settings):
        return 1.8
    return max(
        0.5,
        min(1.8, float(getattr(settings, "v51_memory_context_timeout_seconds", 1.0))),
    )


def current_web_result_limit(settings: Any, *, research_mode: bool, require_current: bool) -> int:
    if research_mode:
        return 10
    if require_current and _enabled(settings):
        return max(4, min(8, int(getattr(settings, "v51_current_web_results", 6))))
    return 8 if require_current else 4


def startup_restore_budget_seconds(settings: Any) -> float:
    if not _enabled(settings):
        return 8.0
    return max(
        0.2,
        min(2.0, float(getattr(settings, "v51_startup_restore_budget_seconds", 0.7))),
    )


def restored_failure_cooldown_seconds(settings: Any) -> float:
    if not _enabled(settings):
        return 0.0
    return max(
        0.0,
        min(180.0, float(getattr(settings, "v51_restored_failure_cooldown_seconds", 90.0))),
    )


def health_snapshot(settings: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v51",
        "name": "Vasuki Speed Lane",
        "enabled": _enabled(settings),
        "cold_start_restore_budget_seconds": startup_restore_budget_seconds(settings),
        "memory_context_timeout_seconds": memory_context_timeout_seconds(settings),
        "context_chars": {
            "fast": int(getattr(settings, "v51_fast_context_chars", 16000)),
            "general": int(getattr(settings, "v51_general_context_chars", 28000)),
            "strong": int(getattr(settings, "v51_strong_context_chars", 42000)),
        },
        "provider_attempts": {
            "fast": int(getattr(settings, "v51_fast_provider_attempts", 3)),
            "general": int(getattr(settings, "v51_general_provider_attempts", 4)),
            "strong": int(getattr(settings, "v51_strong_provider_attempts", 5)),
        },
        "gemini_timeout_seconds": {
            "fast": float(getattr(settings, "v51_gemini_fast_timeout_seconds", 7.5)),
            "general": float(getattr(settings, "v51_gemini_general_timeout_seconds", 11.0)),
            "strong": float(getattr(settings, "v51_gemini_strong_timeout_seconds", 18.0)),
        },
        "current_web_results": int(getattr(settings, "v51_current_web_results", 6)),
        "shared_lookup_skip_enabled": bool(
            getattr(settings, "v51_skip_unneeded_shared_lookup", True)
        ),
        "restored_failure_cooldown_seconds": restored_failure_cooldown_seconds(settings),
        "provider_racing_enabled": False,
        "truth_guard_preserved": True,
        "new_api_key_required": False,
        "new_database_migration_required": False,
        "new_python_dependency_required": False,
    }
