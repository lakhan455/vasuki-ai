from pathlib import Path

from app.v65.connectors import connector_snapshot
from app.v66.multimodal import multimodal_capabilities
from app.v67.reliability import (
    observe_answer_quality,
    observe_live_search,
    observe_truth_guard,
    reliability_snapshot,
)


class DummySettings:
    v11_github_token = "configured"
    tavily_api_key = "configured"
    exa_api = None
    omniroute_search_enabled = False
    omniroute_base_url = ""
    supabase_url = "https://example.supabase.co"
    supabase_secret_key = "secret"
    supabase_service_role_key = None
    v11_stt_api_base_url = ""
    v11_stt_api_key = ""
    v11_tts_api_base_url = ""
    v11_tts_api_key = ""


def test_v65_reports_real_and_future_connectors_honestly():
    rows = connector_snapshot(DummySettings())
    by_id = {row["id"]: row for row in rows}
    assert by_id["github"]["state"] == "connected"
    assert by_id["web"]["configured"] is True
    assert by_id["gmail"]["configured"] is False
    assert by_id["gmail"]["state"] == "connection_backend_required"


def test_v66_browser_voice_is_zero_config():
    caps = multimodal_capabilities(DummySettings())
    assert caps["browser_voice_input"] is True
    assert caps["browser_read_aloud"] is True
    assert caps["audio_upload_transcription"] is False
    assert caps["joint_multimodal_endpoint"] is True


def test_v67_scorecard_tracks_search_quality_without_content():
    observe_live_search(
        ok=True,
        source_count=4,
        duration_ms=900,
        current_required=True,
    )
    observe_answer_quality(
        score=94,
        current_required=True,
        source_count=4,
        provider="test",
    )
    observe_truth_guard("test-guard")
    snap = reliability_snapshot()
    assert snap["metrics"]["current_search_availability_pct"] > 0
    assert snap["metrics"]["average_answer_quality"] > 0
    assert snap["privacy"]["stores_prompts"] is False


def test_v65_v67_production_wiring():
    repo = Path(__file__).resolve().parents[2]

    main = (repo / "backend/app/main.py").read_text(encoding="utf-8")
    main_v5 = (repo / "backend/app/main_v5.py").read_text(encoding="utf-8")
    main_v11 = (repo / "backend/app/main_v11.py").read_text(encoding="utf-8")
    api = (repo / "frontend/lib/api.ts").read_text(encoding="utf-8")
    chat = (repo / "frontend/components/ChatApp.tsx").read_text(encoding="utf-8")
    owner = (repo / "frontend/app/owner/page.tsx").read_text(encoding="utf-8")
    connections = (repo / "frontend/app/connections/page.tsx").read_text(encoding="utf-8")

    assert "observe_live_search" in main
    assert "observe_truth_guard" in main_v5
    assert '"/health/v65"' in main_v11
    assert '"/health/v66"' in main_v11
    assert '"/health/v67"' in main_v11
    assert '"/api/v65/connections"' in main_v11
    assert '"/api/owner/v67/reliability"' in main_v11
    assert "fetchConnectionsV65" in api
    assert 'href="/connections"' in chat
    assert "readResponseAloud" in chat
    assert "fetchOwnerReliabilityV67" in owner
    assert "Connected Apps" in connections
