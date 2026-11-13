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


def test_vasuki_cloud_is_primary_auto_candidate():
    decision = RoutingDecision(
        task_type="general",
        difficulty="normal",
        tier="general",
        language="en",
        needs_web=False,
    )

    assert base_candidates(decision, "auto")[0] == "vasuki_cloud"

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