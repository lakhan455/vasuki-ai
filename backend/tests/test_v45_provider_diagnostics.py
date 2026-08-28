from pathlib import Path

from app.v45.provider_diagnostics import provider_diagnostics_health


def test_v45_health():
    health = provider_diagnostics_health()
    assert health["ok"] is True
    assert health["version"] == "v45"
    assert health["coding_priority"] == ["opencode_zen", "zai_glm"]
    assert health["extra_provider_call_required"] is False


def test_v45_chat_v5_routes_modern_coding_providers():
    backend = Path(__file__).resolve().parents[1]
    source = (backend / "app" / "services" / "chat_v5.py").read_text(
        encoding="utf-8"
    )
    assert '"opencode_zen"' in source
    assert '"zai_glm"' in source
    assert "classify_route(messages)" in source
    assert '"first_token_ms": first_token_ms' in source


def test_v45_main_v5_forwards_diagnostics():
    backend = Path(__file__).resolve().parents[1]
    source = (backend / "app" / "main_v5.py").read_text(encoding="utf-8")
    assert '"provider_model": provider_model' in source
    assert '"first_token_ms": first_token_ms' in source
    assert '"duration_ms": duration_ms' in source


def test_v45_frontend_meta_and_badge():
    repo = Path(__file__).resolve().parents[2]
    api = (repo / "frontend" / "lib" / "api.ts").read_text(encoding="utf-8")
    chat = (repo / "frontend" / "components" / "ChatApp.tsx").read_text(
        encoding="utf-8"
    )
    assert "provider_model?: string;" in api
    assert "first_token_ms?: number;" in api
    assert "duration_ms?: number;" in api
    assert "VASUKI_V45_PROVIDER_BADGE_START" in chat
    assert "pv-provider-diagnostic" in chat


def test_v45_health_endpoint():
    backend = Path(__file__).resolve().parents[1]
    source = (backend / "app" / "main_v11.py").read_text(encoding="utf-8")
    assert "VASUKI_V45_PROVIDER_DIAGNOSTICS_INTEGRATION" in source
    assert '@app.get("/health/v45")' in source
