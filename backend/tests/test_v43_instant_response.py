from pathlib import Path

from app.v43.instant_response import instant_response_health


def test_v43_health_contract_is_truthful():
    health = instant_response_health()
    assert health["ok"] is True
    assert health["version"] == "v43"
    assert health["intent_ui_target_ms"] == 100
    assert health["intent_ui_hard_guarantee"] is False
    assert health["full_ai_answer_in_100ms_guaranteed"] is False
    assert health["fake_answer_used"] is False


def test_v43_intent_is_local_and_network_free():
    health = instant_response_health()
    assert health["intent_requires_provider_call"] is False
    assert health["intent_requires_network_roundtrip"] is False
    assert health["real_answer_streaming_preserved"] is True


def test_v43_preserves_existing_runtime_layers():
    health = instant_response_health()
    assert health["v42_dual_provider_preserved"] is True
    assert health["v41_weather_preserved"] is True
    assert health["v40_creator_runtime_preserved"] is True


def test_v43_frontend_instant_intent_integration_present():
    repo = Path(__file__).resolve().parents[2]
    source = (repo / "frontend" / "components" / "ChatApp.tsx").read_text(
        encoding="utf-8"
    )
    assert "VASUKI_V43_INSTANT_INTENT_START" in source
    assert "function instantIntentStatus(" in source
    assert "setInstantIntent(instantStatus);" in source
    assert 'aria-label="Starting response"' in source


def test_v43_intent_clears_on_real_token_and_completion():
    repo = Path(__file__).resolve().parents[2]
    source = (repo / "frontend" / "components" / "ChatApp.tsx").read_text(
        encoding="utf-8"
    )
    assert 'const onStreamToken = (token: string) => {\n          setInstantIntent("");' in source
    assert 'activeCodeJobRef.current = null;\n      setInstantIntent("");' in source


def test_v43_main_health_endpoint_present():
    backend = Path(__file__).resolve().parents[1]
    source = (backend / "app" / "main_v11.py").read_text(encoding="utf-8")
    assert "VASUKI_V43_INSTANT_INTENT_RESPONSE_INTEGRATION" in source
    assert '@app.get("/health/v43")' in source
