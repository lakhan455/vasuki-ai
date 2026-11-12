from app.config import Settings
from app.services.chat import _stream_provider_config
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