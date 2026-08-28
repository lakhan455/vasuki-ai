from pathlib import Path
from types import SimpleNamespace

from app.v46.adaptive_speed import (
    adaptive_provider_order,
    adaptive_speed_health,
    first_token_timeout_seconds,
    record_provider_failure,
    record_provider_success,
    reset_speed_stats,
    speed_snapshot,
)


def setup_function():
    reset_speed_stats()


def test_v46_preserves_code_order_before_learning():
    order = ["opencode_zen", "zai_glm", "groq"]
    assert adaptive_provider_order(order, "code", min_samples=2) == order


def test_v46_learns_faster_code_provider_inside_quality_band():
    for _ in range(2):
        record_provider_success("opencode_zen", 1800, "code")
        record_provider_success("zai_glm", 900, "code")
    ranked = adaptive_provider_order(["opencode_zen", "zai_glm", "groq"], "code", min_samples=2)
    assert ranked[:2] == ["zai_glm", "opencode_zen"]
    assert ranked[2] == "groq"


def test_v46_research_order_is_not_reordered():
    for _ in range(3):
        record_provider_success("gemini", 100, "research")
        record_provider_success("groq", 900, "research")
    order = ["groq", "gemini", "openrouter"]
    assert adaptive_provider_order(order, "research", min_samples=2) == order


def test_v46_failure_penalty_is_recorded():
    record_provider_success("groq_fast", 400, "general")
    record_provider_failure("groq_fast", "general")
    rows = speed_snapshot()["providers"]
    assert rows[0]["provider"] == "groq_fast"
    assert rows[0]["failures"] == 1


def test_v46_timeouts_are_task_aware():
    settings = SimpleNamespace(
        v46_simple_first_token_timeout_seconds=1.1,
        v46_code_first_token_timeout_seconds=2.4,
        v46_large_first_token_timeout_seconds=3.2,
    )
    assert first_token_timeout_seconds("general", large_request=False, settings=settings) == 1.1
    assert first_token_timeout_seconds("code", large_request=False, settings=settings) == 2.4
    assert first_token_timeout_seconds("code", large_request=True, settings=settings) == 3.2


def test_v46_health_has_no_extra_provider_calls():
    settings = SimpleNamespace(
        v46_adaptive_speed_enabled=True,
        v46_adaptive_min_samples=2,
        v46_simple_first_token_timeout_seconds=1.25,
        v46_code_first_token_timeout_seconds=2.2,
        v46_large_first_token_timeout_seconds=3.0,
    )
    health = adaptive_speed_health(settings)
    assert health["version"] == "v46"
    assert health["provider_racing_enabled"] is False
    assert health["extra_provider_call_required"] is False
    assert health["db_migration_required"] is False


def test_v46_chat_stream_signature_supports_regenerate_options():
    backend = Path(__file__).resolve().parents[1]
    source = (backend / "app" / "services" / "chat_v5.py").read_text(encoding="utf-8")
    assert "cache_bypass: bool = False" in source
    assert "exclude_provider: str | None = None" in source
    assert "adaptive_provider_order(" in source


def test_v46_main_health_endpoint_present():
    backend = Path(__file__).resolve().parents[1]
    source = (backend / "app" / "main_v11.py").read_text(encoding="utf-8")
    assert "VASUKI_V46_ADAPTIVE_SPEED_INTEGRATION" in source
    assert '@app.get("/health/v46")' in source


def test_v46_frontend_exposes_fallback_count():
    repo = Path(__file__).resolve().parents[2]
    api = (repo / "frontend" / "lib" / "api.ts").read_text(encoding="utf-8")
    app = (repo / "frontend" / "components" / "ChatApp.tsx").read_text(encoding="utf-8")
    assert "attempt_count?: number;" in api
    assert "attemptCount?: number;" in app
    assert "fallback" in app
