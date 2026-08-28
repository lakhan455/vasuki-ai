from pathlib import Path
from types import SimpleNamespace

from app.v47.reliability_router import (
    adaptive_reliability_order,
    first_token_timeout_for_provider,
    observe_provider_failure,
    observe_provider_success,
    provider_available,
    reliability_snapshot,
    reset_reliability_stats,
    v47_health,
)


def settings():
    return SimpleNamespace(
        v47_reliability_router_enabled=True,
        v47_persistent_learning_enabled=True,
        v47_adaptive_min_samples=2,
        v47_circuit_failure_threshold=2,
        v47_circuit_base_cooldown_seconds=45.0,
        v47_circuit_max_cooldown_seconds=900.0,
        v47_first_token_timeout_floor_seconds=1.0,
        v47_simple_first_token_timeout_max_seconds=3.5,
        v47_code_first_token_timeout_max_seconds=5.5,
        v47_large_first_token_timeout_max_seconds=7.0,
        v46_simple_first_token_timeout_seconds=1.25,
        v46_code_first_token_timeout_seconds=2.2,
        v46_large_first_token_timeout_seconds=3.0,
        v18_chat_recovery_first_token_seconds=4.5,
    )


def setup_function():
    reset_reliability_stats()


def test_v47_preserves_quality_order_before_samples():
    s = settings()
    base = ["opencode_zen", "zai_glm", "groq", "openrouter"]
    assert adaptive_reliability_order(base, "code", "strong", s) == base


def test_v47_promotes_faster_reliable_provider_inside_quality_band():
    s = settings()
    for _ in range(3):
        observe_provider_success(
            "opencode_zen", "code", first_token_ms=2100, total_latency_ms=6200
        )
        observe_provider_success(
            "zai_glm", "code", first_token_ms=850, total_latency_ms=4100
        )
    ranked = adaptive_reliability_order(
        ["opencode_zen", "zai_glm", "groq", "openrouter"],
        "code",
        "strong",
        s,
    )
    assert ranked[0] == "zai_glm"
    assert ranked[-1] == "openrouter"


def test_v47_circuit_opens_after_repeated_failures():
    s = settings()
    observe_provider_failure("groq", "general", "timeout", s)
    observe_provider_failure("groq", "general", "timeout", s)
    assert provider_available("groq", "general") is False
    row = reliability_snapshot()["providers"][0]
    assert row["circuit_open"] is True
    assert row["consecutive_failures"] == 2


def test_v47_success_closes_circuit():
    s = settings()
    observe_provider_failure("groq", "general", "timeout", s)
    observe_provider_failure("groq", "general", "timeout", s)
    observe_provider_success(
        "groq", "general", first_token_ms=500, total_latency_ms=1700
    )
    assert provider_available("groq", "general") is True


def test_v47_provider_specific_timeout_learns_from_latency():
    s = settings()
    for _ in range(3):
        observe_provider_success(
            "zai_glm", "code", first_token_ms=900, total_latency_ms=3000
        )
    learned = first_token_timeout_for_provider(
        "zai_glm", "code", tier="strong", settings=s
    )
    assert 1.0 <= learned <= 7.0
    assert learned < 3.0


def test_v47_health_contract_requires_no_migration_or_provider_call():
    health = v47_health(settings())
    assert health["version"] == "v47"
    assert health["db_migration_required"] is False
    assert health["reuses_v11_provider_quality_table"] is True
    assert health["extra_provider_call_required"] is False
    assert health["provider_racing_enabled"] is False


def test_v47_is_wired_into_production_chat_v7():
    backend = Path(__file__).resolve().parents[1]
    source = (backend / "app" / "services" / "chat_v7.py").read_text(encoding="utf-8")
    assert "adaptive_reliability_order(" in source
    assert "first_token_timeout_for_provider(" in source
    assert '"router_version": "v47"' in source
    assert "observe_provider_success(" in source
    assert "observe_provider_failure(" in source


def test_v47_health_and_startup_restore_are_wired():
    backend = Path(__file__).resolve().parents[1]
    source = (backend / "app" / "main_v11.py").read_text(encoding="utf-8")
    assert "VASUKI_V47_SELF_HEALING_ROUTER_INTEGRATION" in source
    assert '@app.get("/health/v47")' in source
    assert "await load_persisted_reliability(settings)" in source


def test_v47_frontend_surfaces_router_health():
    repo = Path(__file__).resolve().parents[2]
    api = (repo / "frontend" / "lib" / "api.ts").read_text(encoding="utf-8")
    app = (repo / "frontend" / "components" / "ChatApp.tsx").read_text(encoding="utf-8")
    assert "router_version?: string;" in api
    assert "reliability_score?: number;" in api
    assert "routerVersion?: string;" in app
    assert "reliabilityScore?: number;" in app
