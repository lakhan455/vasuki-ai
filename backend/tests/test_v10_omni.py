from __future__ import annotations

from app.config import Settings
from app.services.omniroute_gateway_v10 import configured, route_profile
from app.services.omniroute_knowledge_v10 import corpus_info, search_omniroute_knowledge


def test_v10_route_profiles():
    assert route_profile("simple") == ("auto/fast", "fast")
    assert route_profile("code") == ("auto/coding:reliable", "reliable")
    assert route_profile("reasoning") == ("auto/reasoning:reliable", "quality")
    assert route_profile("research", require_current=True) == ("auto/reasoning:reliable", "reliable")
    assert route_profile("general") == ("auto", "balanced")


def test_v10_gateway_config_requires_enabled_and_url():
    base = Settings()
    assert configured(base) is False

    enabled = Settings(omniroute_enabled=True, omniroute_base_url="https://omni.example")
    assert configured(enabled) is True


def test_v10_knowledge_corpus_is_available():
    info = corpus_info()
    assert info["available"] is True
    assert int(info["chunks"]) >= 1000
    assert int(info["files_indexed"]) >= 100


def test_v10_knowledge_search_finds_auto_combo():
    results = search_omniroute_knowledge(
        "OmniRoute auto coding reliable circuit breaker quota routing",
        limit=5,
    )
    assert results
    joined = "\n".join(
        f"{item['path']} {item['section']} {item['text']}" for item in results
    ).casefold()
    assert "auto" in joined
    assert "routing" in joined or "combo" in joined
