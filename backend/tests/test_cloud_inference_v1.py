from app.config import Settings
from app.services.chat import (
    _stream_provider_config,
    _vasuki_cloud_gradio_prompt,
    _vasuki_cloud_transport,
)
from app.v47.reliability_router import (
    first_token_timeout_for_provider,
)
from app.services.router_v7 import (
    RoutingDecision,
    apply_auto_provider_policy,
    base_candidates,
    configured_provider,
)


def _settings(**kwargs):
    return Settings(_env_file=None, **kwargs)


def test_vasuki_cloud_disabled_by_default():
    settings = _settings()
    assert configured_provider("vasuki_cloud", settings) is False


def test_vasuki_cloud_configuration():
    settings = _settings(
        vasuki_cloud_enabled=True,
        vasuki_cloud_base_url="https://inference.example.com/v1",
        vasuki_cloud_api_key="internal-test-key",
        vasuki_cloud_model="vasuki-main",
    )

    assert configured_provider("vasuki_cloud", settings) is True

    url, key, model, token_field, headers = _stream_provider_config(
        "vasuki_cloud",
        settings,
    )

    assert url == "https://inference.example.com/v1/chat/completions"
    assert key == "internal-test-key"
    assert model == "vasuki-main"
    assert token_field == "max_tokens"
    assert headers == {}


def test_vasuki_cloud_auto_policy_defaults_to_fallback():
    decision = RoutingDecision(
        task_type="general",
        difficulty="normal",
        tier="general",
        language="en",
        needs_web=False,
    )
    settings = _settings()

    base = base_candidates(decision, "auto")
    ordered = apply_auto_provider_policy(
        base,
        "auto",
        settings,
    )

    assert ordered[-1] == "vasuki_cloud"
    assert ordered[0] != "vasuki_cloud"


def test_vasuki_cloud_auto_primary_can_be_enabled():
    decision = RoutingDecision(
        task_type="general",
        difficulty="normal",
        tier="general",
        language="en",
        needs_web=False,
    )
    settings = _settings(
        vasuki_cloud_auto_primary=True,
    )

    ordered = apply_auto_provider_policy(
        base_candidates(decision, "auto"),
        "auto",
        settings,
    )

    assert ordered[0] == "vasuki_cloud"


def test_explicit_vasuki_cloud_route_is_unchanged():
    settings = _settings()

    assert apply_auto_provider_policy(
        ["vasuki_cloud"],
        "vasuki_cloud",
        settings,
    ) == ["vasuki_cloud"]

def test_vasuki_cloud_gradio_configuration_without_external_api_key():
    settings = _settings(
        vasuki_cloud_enabled=True,
        vasuki_cloud_transport="gradio",
        vasuki_cloud_space_id="lakhan455/vasuki-ai-zerogpu",
        vasuki_cloud_gradio_api_name="/chat",
        vasuki_cloud_base_url="",
        vasuki_cloud_api_key=None,
    )

    assert configured_provider(
        "vasuki_cloud",
        settings,
    ) is True

    assert _vasuki_cloud_transport(
        settings
    ) == "gradio"


def test_vasuki_cloud_gradio_requires_space_id():
    settings = _settings(
        vasuki_cloud_enabled=True,
        vasuki_cloud_transport="gradio",
        vasuki_cloud_space_id="",
    )

    assert configured_provider(
        "vasuki_cloud",
        settings,
    ) is False


def test_vasuki_cloud_gradio_prompt_preserves_context():
    prompt = _vasuki_cloud_gradio_prompt(
        [
            {
                "role": "user",
                "content": "What is the answer?",
            }
        ],
        "Verified evidence: 42.",
        require_current=True,
        as_of="2026-11-12",
    )

    assert "Verified evidence: 42." in prompt
    assert "USER: What is the answer?" in prompt
    assert "2026-11-12" in prompt


def test_vasuki_cloud_gradio_gets_queue_aware_timeout():
    settings = _settings(
        vasuki_cloud_enabled=True,
        vasuki_cloud_transport="gradio",
        vasuki_cloud_space_id=(
            "lakhan455/vasuki-ai-zerogpu"
        ),
        vasuki_cloud_gradio_first_token_timeout_seconds=50.0,
        total_chat_timeout_seconds=55,
    )

    timeout = first_token_timeout_for_provider(
        "vasuki_cloud",
        "general",
        tier="general",
        settings=settings,
    )

    assert timeout == 50.0
def test_vasuki_cloud_startup_probe_disabled(monkeypatch):
    import asyncio
    from app.services import cloud_probe

    async def should_not_run(*args, **kwargs):
        raise AssertionError(
            "cloud provider should not run while probe is disabled"
        )

    monkeypatch.setattr(
        cloud_probe,
        "chat_vasuki_cloud",
        should_not_run,
    )

    settings = _settings(
        vasuki_cloud_enabled=True,
        vasuki_cloud_startup_probe=False,
    )

    result = asyncio.run(
        cloud_probe.run_cloud_startup_probe(settings)
    )

    assert result["ran"] is False
    assert result["status"] == "disabled"


def test_vasuki_cloud_startup_probe_success(monkeypatch):
    import asyncio
    from app.services import cloud_probe

    async def fake_cloud(
        messages,
        settings,
        web_context="",
        **kwargs,
    ):
        assert messages[-1]["content"] == (
            "Reply only with: VASUKI CLOUD READY"
        )
        return "VASUKI CLOUD READY"

    monkeypatch.setattr(
        cloud_probe,
        "chat_vasuki_cloud",
        fake_cloud,
    )

    settings = _settings(
        vasuki_cloud_enabled=True,
        vasuki_cloud_startup_probe=True,
    )

    result = asyncio.run(
        cloud_probe.run_cloud_startup_probe(settings)
    )

    assert result["ran"] is True
    assert result["ok"] is True
    assert result["status"] == "success"
    assert result["latency_ms"] >= 0


def test_vasuki_cloud_startup_probe_failure_is_nonfatal(
    monkeypatch,
):
    import asyncio
    from app.services import cloud_probe

    async def failing_cloud(*args, **kwargs):
        raise RuntimeError("simulated provider failure")

    monkeypatch.setattr(
        cloud_probe,
        "chat_vasuki_cloud",
        failing_cloud,
    )

    settings = _settings(
        vasuki_cloud_enabled=True,
        vasuki_cloud_startup_probe=True,
    )

    result = asyncio.run(
        cloud_probe.run_cloud_startup_probe(settings)
    )

    assert result["ran"] is True
    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["error_type"] == "RuntimeError"


def test_vasuki_cloud_gradio_stream_delta_modes():
    from app.services.chat import _gradio_stream_delta

    delta, state = _gradio_stream_delta("", "Hel")
    assert delta == "Hel"
    assert state == "Hel"

    # Cumulative generator output.
    delta, state = _gradio_stream_delta(
        state,
        "Hello",
    )
    assert delta == "lo"
    assert state == "Hello"

    # Raw incremental token output.
    delta, state = _gradio_stream_delta(
        state,
        " world",
    )
    assert delta == " world"
    assert state == "Hello world"


def test_vasuki_cloud_stream_provider_segment_uses_live_gradio(
    monkeypatch,
):
    import asyncio

    from app.services import chat as legacy_chat
    from app.services.chat_v5 import _stream_provider_segment

    async def fake_live_stream(
        messages,
        settings,
        web_context="",
        *,
        require_current,
        as_of,
    ):
        assert messages[-1]["content"] == "hello"
        yield "Hello"
        yield " "
        yield "world"

    monkeypatch.setattr(
        legacy_chat,
        "_stream_vasuki_cloud_gradio",
        fake_live_stream,
    )

    settings = _settings(
        vasuki_cloud_enabled=True,
        vasuki_cloud_transport="gradio",
        vasuki_cloud_space_id=(
            "lakhan455/vasuki-ai-zerogpu"
        ),
    )

    async def collect():
        return [
            event
            async for event in _stream_provider_segment(
                name="vasuki_cloud",
                messages=[
                    {
                        "role": "user",
                        "content": "hello",
                    }
                ],
                settings=settings,
                web_context="",
                require_current=False,
                as_of=None,
                large_request=False,
            )
        ]

    events = asyncio.run(collect())

    tokens = [
        event["token"]
        for event in events
        if event.get("type") == "token"
    ]

    assert tokens == [
        "Hello",
        " ",
        "world",
    ]

    assert events[-1]["type"] == "finish"
    assert events[-1]["reason"] == "stop"


def test_vasuki_cloud_stream_startup_probe_success(
    monkeypatch,
):
    import asyncio

    from app.services import cloud_probe

    async def fake_stream(
        messages,
        settings,
        web_context="",
        *,
        require_current,
        as_of,
    ):
        assert (
            messages[-1]["content"]
            == cloud_probe._STREAM_CANARY_PROMPT
        )

        yield "VASUKI "
        yield "STREAM READY ONE TWO THREE "
        yield "FOUR FIVE SIX SEVEN EIGHT NINE TEN"

    monkeypatch.setattr(
        cloud_probe,
        "_stream_vasuki_cloud_gradio",
        fake_stream,
    )

    settings = _settings(
        vasuki_cloud_enabled=True,
        vasuki_cloud_transport="gradio",
        vasuki_cloud_stream_startup_probe=True,
    )

    result = asyncio.run(
        cloud_probe.run_cloud_stream_startup_probe(
            settings
        )
    )

    assert result["ran"] is True
    assert result["ok"] is True
    assert result["status"] == "success"
    assert result["chunk_count"] == 3
    assert result["first_chunk_ms"] is not None


def test_vasuki_cloud_stream_probe_rejects_single_chunk(
    monkeypatch,
):
    import asyncio

    from app.services import cloud_probe

    async def fake_stream(*args, **kwargs):
        yield (
            "VASUKI STREAM READY ONE TWO THREE "
            "FOUR FIVE SIX SEVEN EIGHT NINE TEN"
        )

    monkeypatch.setattr(
        cloud_probe,
        "_stream_vasuki_cloud_gradio",
        fake_stream,
    )

    settings = _settings(
        vasuki_cloud_enabled=True,
        vasuki_cloud_transport="gradio",
        vasuki_cloud_stream_startup_probe=True,
    )

    result = asyncio.run(
        cloud_probe.run_cloud_stream_startup_probe(
            settings
        )
    )

    assert result["ran"] is True
    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["chunk_count"] == 1
    assert result["error_type"] == "RuntimeError"
