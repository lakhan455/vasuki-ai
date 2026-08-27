from pathlib import Path
from types import SimpleNamespace

from app.services import chat as legacy_chat
from app.services.router_v7 import RoutingDecision, base_candidates, configured_provider
from app.v17.provider_recovery import CODE_PROVIDER_ORDER
from app.v44.zai_glm import zai_glm_health


def _settings(**kwargs):
    base = {
        "groq_api_key": None,
        "sambanova_api_key": None,
        "cerebras_api_key": None,
        "google_gemini_api": None,
        "opencode_zen_api_key": "zen-secret",
        "openrouter_api": "or-secret",
        "mistral_ai_api": None,
        "zai_api_key": "zai-secret",
        "zai_coding_base_url": "https://api.z.ai/api/coding/paas/v4",
        "zai_model": "glm-4.7",
        "app_name": "Vasuki AI",
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_v44_zai_is_configured():
    assert configured_provider("zai_glm", _settings()) is True


def test_v44_zai_is_second_coding_provider():
    d = RoutingDecision("code", "complex", "strong", "en", False)
    assert base_candidates(d, "auto")[:2] == ["opencode_zen", "zai_glm"]


def test_v44_builder_has_zai_after_zen():
    assert CODE_PROVIDER_ORDER[:2] == ("opencode_zen", "zai_glm")


def test_v44_stream_endpoint_uses_coding_plan_url():
    url, key, model, token_field, headers = legacy_chat._stream_provider_config(
        "zai_glm", _settings()
    )
    assert url == "https://api.z.ai/api/coding/paas/v4/chat/completions"
    assert key == "zai-secret"
    assert model == "glm-4.7"
    assert token_field == "max_tokens"
    assert headers == {}


def test_v44_health_does_not_expose_secret():
    health = zai_glm_health(_settings())
    assert health["zai_glm"]["configured"] is True
    assert health["zai_glm"]["coding_priority"] == 2
    assert "zai-secret" not in str(health)
    assert health["api_key_exposed_to_frontend"] is False


def test_v44_config_has_backend_only_settings():
    backend = Path(__file__).resolve().parents[1]
    source = (backend / "app" / "config.py").read_text(encoding="utf-8")
    assert "zai_api_key: str | None = None" in source
    assert 'zai_model: str = "glm-4.7"' in source


def test_v44_env_example_has_placeholders_only():
    backend = Path(__file__).resolve().parents[1]
    source = (backend / ".env.example").read_text(encoding="utf-8")
    assert "ZAI_API_KEY=" in source
    assert "ZAI_MODEL=glm-4.7" in source
    assert "ZAI_API_KEY=zai-secret" not in source


def test_v44_main_health_endpoint_present():
    backend = Path(__file__).resolve().parents[1]
    source = (backend / "app" / "main_v11.py").read_text(encoding="utf-8")
    assert "VASUKI_V44_ZAI_GLM_CODING_INTEGRATION" in source
    assert '@app.get("/health/v44")' in source
