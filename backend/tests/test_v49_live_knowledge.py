from types import SimpleNamespace

from app.v49.live_knowledge import DEFAULT_TOPICS, live_knowledge_status, observe_current_query


def _settings(**overrides):
    base = dict(
        v49_live_knowledge_enabled=True,
        v49_refresh_interval_seconds=7200,
        v49_topics_per_cycle=2,
        tavily_api_key="tavily",
        exa_api=None,
        omniroute_enabled=False,
        omniroute_search_enabled=False,
        omniroute_base_url="",
        global_learning_configured=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_v49_default_topics_include_all_india_cm_snapshot():
    topic = next(item for item in DEFAULT_TOPICS if item.id == "india-state-chief-ministers")
    assert topic.require_all_india_state_entities is True
    assert "all 28 Indian states" in topic.question
    assert "ind ke saare cm ki list" in topic.aliases


def test_v49_status_reports_search_storage_and_no_new_migration():
    status = live_knowledge_status(_settings())
    assert status["version"] == "v49"
    assert status["search_ready"] is True
    assert status["storage_ready"] is True
    assert status["new_database_migration_required"] is False
    assert status["new_api_key_required"] is False


def test_v49_adaptive_queue_rejects_sensitive_data():
    assert observe_current_query("latest RBI repo rate today") is True
    assert observe_current_query("my password is hello123 latest") is False
    assert observe_current_query("email me at user@example.com latest") is False


def test_v49_source_is_wired_into_production_files():
    from pathlib import Path
    backend = Path(__file__).resolve().parents[1]
    main = (backend / "app" / "main_v11.py").read_text(encoding="utf-8")
    legacy = (backend / "app" / "main.py").read_text(encoding="utf-8")
    config = (backend / "app" / "config.py").read_text(encoding="utf-8")
    assert "VASUKI_V49_CONTINUOUS_LIVE_KNOWLEDGE" in main
    assert "build_v49_router" in main
    assert "v49_live_knowledge_loop" in main
    assert "observe_current_query" in legacy
    assert "v49_refresh_interval_seconds" in config
