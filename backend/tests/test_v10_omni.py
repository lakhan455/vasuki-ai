from __future__ import annotations

from app.config import Settings
from app.services.chat_v10 import (
    _should_bypass_omniroute,
)
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


def test_v10_fast_lane_bypass_policy():
    from types import SimpleNamespace

    settings = Settings(
        _env_file=None,
    )

    assert _should_bypass_omniroute(
        SimpleNamespace(tier="fast"),
        settings,
    ) is True

    assert _should_bypass_omniroute(
        SimpleNamespace(tier="strong"),
        settings,
    ) is False

    disabled = Settings(
        _env_file=None,
        omniroute_fast_lane_bypass=False,
    )

    assert _should_bypass_omniroute(
        SimpleNamespace(tier="fast"),
        disabled,
    ) is False


def test_v10_fast_prompt_uses_direct_vasuki_lane(
    monkeypatch,
):
    import asyncio
    import app.services.chat_v10 as chat_v10

    calls = []

    async def fake_v7(
        provider,
        messages,
        settings,
        web_context="",
        **kwargs,
    ):
        calls.append(provider)

        yield {
            "type": "provider",
            "provider": "groq_fast",
        }

        yield {
            "type": "token",
            "token": "Hi!",
        }

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Fast request should bypass OmniRoute"
        )

    monkeypatch.setattr(
        chat_v10,
        "route_chat_stream_v7",
        fake_v7,
    )

    monkeypatch.setattr(
        chat_v10,
        "omniroute_stream_chat",
        forbidden,
    )

    monkeypatch.setattr(
        chat_v10,
        "omniroute_configured",
        forbidden,
    )

    monkeypatch.setattr(
        chat_v10,
        "omniroute_context",
        forbidden,
    )

    settings = Settings(
        _env_file=None,
        omniroute_enabled=True,
        omniroute_base_url=(
            "https://omni.example"
        ),
        omniroute_fast_lane_bypass=True,
    )

    async def collect():
        return [
            event
            async for event
            in chat_v10.route_chat_stream_v10(
                "auto",
                [
                    {
                        "role": "user",
                        "content": "hi",
                    }
                ],
                settings,
            )
        ]

    events = asyncio.run(collect())

    assert calls == ["auto"]

    assert any(
        event.get("provider")
        == "groq_fast"
        for event in events
    )

    assert "".join(
        event.get("token", "")
        for event in events
        if event.get("type") == "token"
    ) == "Hi!"
