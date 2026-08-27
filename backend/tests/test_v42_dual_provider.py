from pathlib import Path
from types import SimpleNamespace

from app.services import chat as legacy_chat
from app.services.router_v7 import RoutingDecision, base_candidates, configured_provider
from app.v17.provider_recovery import CODE_PROVIDER_ORDER
from app.v42.dual_provider import dual_provider_health


def _settings(**kwargs):
    base = {
        "opencode_zen_api_key": "zen-secret",
        "opencode_zen_base_url": "https://opencode.ai/zen/v1",
        "opencode_zen_model": "north-mini-code-free",
        "openrouter_api": "or-secret",
        "openrouter_model": "openai/gpt-4.1-mini",
        "openrouter_image_enabled": False,
        "openrouter_image_model": "",
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_v42_zen_is_configured():
    assert configured_provider("opencode_zen", _settings()) is True


def test_v42_code_auto_order_is_zen_first():
    d = RoutingDecision(task_type="code", difficulty="complex", tier="strong", language="en", needs_web=False)
    order = base_candidates(d, "auto")
    assert order[0] == "opencode_zen"
    assert "openrouter" in order


def test_v42_autonomous_builder_prefers_zen():
    assert CODE_PROVIDER_ORDER[0] == "opencode_zen"
    assert "openrouter" in CODE_PROVIDER_ORDER


def test_v42_zen_stream_endpoint():
    url, key, model, token_field, headers = legacy_chat._stream_provider_config("opencode_zen", _settings())
    assert url == "https://opencode.ai/zen/v1/chat/completions"
    assert key == "zen-secret"
    assert model == "north-mini-code-free"
    assert token_field == "max_tokens"
    assert headers == {}


def test_v42_health_never_exposes_keys():
    health = dual_provider_health(_settings())
    blob = str(health)
    assert "zen-secret" not in blob
    assert "or-secret" not in blob
    assert health["api_keys_exposed_to_frontend"] is False


def test_v42_openrouter_image_requires_opt_in():
    health = dual_provider_health(_settings())
    assert health["openrouter"]["image_enabled"] is False
    assert health["openrouter"]["image_configured"] is False


def test_v42_openrouter_image_can_be_configured():
    health = dual_provider_health(_settings(openrouter_image_enabled=True, openrouter_image_model="google/gemini-2.5-flash-image"))
    assert health["openrouter"]["image_configured"] is True


def test_v42_config_and_env_are_backend_only_placeholders():
    backend = Path(__file__).resolve().parents[1]
    config = (backend / "app" / "config.py").read_text(encoding="utf-8")
    env = (backend / ".env.example").read_text(encoding="utf-8")
    assert "opencode_zen_api_key: str | None = None" in config
    assert "OPENCODE_ZEN_API_KEY=" in env
    assert "OPENROUTER_IMAGE_ENABLED=false" in env


def test_v42_main_health_endpoint_present():
    backend = Path(__file__).resolve().parents[1]
    source = (backend / "app" / "main_v11.py").read_text(encoding="utf-8")
    assert "VASUKI_V42_DUAL_PROVIDER_CODING_IMAGE_INTEGRATION" in source
    assert '@app.get("/health/v42")' in source
