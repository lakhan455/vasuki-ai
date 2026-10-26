from pathlib import Path
from types import SimpleNamespace

from app.v51.speed_lane import (
    context_policy,
    current_web_result_limit,
    gemini_timeout_seconds,
    health_snapshot,
    provider_attempt_budget,
    should_lookup_shared_knowledge,
    startup_restore_budget_seconds,
)


def settings():
    return SimpleNamespace(
        v51_speed_lane_enabled=True,
        max_context_chars=45000,
        max_provider_attempts=7,
        v51_fast_context_chars=16000,
        v51_general_context_chars=28000,
        v51_strong_context_chars=42000,
        v51_fast_provider_attempts=3,
        v51_general_provider_attempts=4,
        v51_strong_provider_attempts=5,
        v51_gemini_fast_timeout_seconds=7.5,
        v51_gemini_general_timeout_seconds=11.0,
        v51_gemini_strong_timeout_seconds=18.0,
        v51_current_web_results=6,
        v51_skip_unneeded_shared_lookup=True,
        v51_startup_restore_budget_seconds=0.7,
        v51_memory_context_timeout_seconds=1.0,
        v51_restored_failure_cooldown_seconds=90.0,
    )


def decision(task_type="general", tier="balanced"):
    return SimpleNamespace(task_type=task_type, tier=tier)


def test_v51_fast_context_is_bounded():
    assert context_policy(decision("simple", "fast"), settings()) == (16000, 8)


def test_v51_strong_context_preserves_quality_budget():
    assert context_policy(decision("research", "strong"), settings()) == (42000, 12)


def test_v51_attempt_budget_is_task_aware():
    s = settings()
    assert provider_attempt_budget(decision("simple", "fast"), s) == 3
    assert provider_attempt_budget(decision("general", "balanced"), s) == 4
    assert provider_attempt_budget(decision("code", "strong"), s) == 5
    assert provider_attempt_budget(decision("code", "strong"), s, provider="groq") == 1


def test_v51_gemini_fallback_timeout_is_bounded():
    s = settings()
    assert gemini_timeout_seconds(decision("simple", "fast"), s) == 7.5
    assert gemini_timeout_seconds(decision("general", "balanced"), s) == 11.0
    assert gemini_timeout_seconds(decision("reasoning", "strong"), s) == 18.0


def test_v51_shared_lookup_skips_unneeded_work():
    s = settings()
    assert should_lookup_shared_knowledge(
        direct_fact=False,
        current_required=False,
        authoritative_snapshot_candidate=False,
        settings=s,
    ) is False
    assert should_lookup_shared_knowledge(
        direct_fact=True,
        current_required=False,
        authoritative_snapshot_candidate=False,
        settings=s,
    ) is True
    assert should_lookup_shared_knowledge(
        direct_fact=False,
        current_required=True,
        authoritative_snapshot_candidate=True,
        settings=s,
    ) is True


def test_v51_current_web_results_keep_verification_room():
    s = settings()
    assert current_web_result_limit(s, research_mode=False, require_current=True) == 6
    assert current_web_result_limit(s, research_mode=True, require_current=True) == 10


def test_v51_startup_restore_is_bounded():
    assert startup_restore_budget_seconds(settings()) == 0.7


def test_v51_health_contract():
    health = health_snapshot(settings())
    assert health["version"] == "v51"
    assert health["provider_racing_enabled"] is False
    assert health["truth_guard_preserved"] is True
    assert health["new_api_key_required"] is False
    assert health["new_database_migration_required"] is False


def test_v51_integrations_are_wired():
    backend = Path(__file__).resolve().parents[1]
    main = (backend / "app" / "main.py").read_text(encoding="utf-8")
    main_v11 = (backend / "app" / "main_v11.py").read_text(encoding="utf-8")
    chat_v7 = (backend / "app" / "services" / "chat_v7.py").read_text(encoding="utf-8")
    reliability = (backend / "app" / "v47" / "reliability_router.py").read_text(encoding="utf-8")

    assert "_v51_shared_knowledge(" in main
    assert "asyncio.gather(" in main
    assert "provider_attempt_budget(" in chat_v7
    assert "context_policy(" in chat_v7
    assert "gemini_timeout_seconds(" in chat_v7
    assert "v51_restored_failure_cooldown_seconds" in reliability
    assert '@app.get("/health/v51")' in main_v11
