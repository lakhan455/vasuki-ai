from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.v49.current_facts import (
    CM_SNAPSHOT_MARKER,
    _parse_json_results,
    _validate_candidate,
    extract_recent_cm_snapshot,
)


def _official(content: str, url: str = "https://state.gov.in/cm"):
    return {
        "title": "Chief Minister",
        "url": url,
        "content": content,
        "source_type": "official",
        "entity": "Example State",
    }


def test_parser_accepts_strict_results_json():
    raw = '{"results":[{"state":"Example State","chief_minister":"Asha Rao","confidence":0.95,"status":"verified","evidence_urls":["https://state.gov.in/cm"]}]}'
    parsed = _parse_json_results(raw)
    assert parsed[0]["chief_minister"] == "Asha Rao"


def test_validator_accepts_official_current_cm_evidence():
    evidence = [_official("Asha Rao is the current Chief Minister of Example State.")]
    result = {
        "state": "Example State",
        "chief_minister": "Asha Rao",
        "confidence": 0.95,
        "status": "verified",
        "evidence_urls": ["https://state.gov.in/cm"],
    }
    fact = _validate_candidate("Example State", result, evidence, min_confidence=0.84)
    assert fact is not None
    assert fact.chief_minister == "Asha Rao"


def test_validator_rejects_deputy_cm_as_cm():
    evidence = [
        _official(
            "Asha Rao is the Deputy Chief Minister of Example State.",
            "https://state.gov.in/deputy-cm",
        )
    ]
    result = {
        "state": "Example State",
        "chief_minister": "Asha Rao",
        "confidence": 0.99,
        "status": "verified",
        "evidence_urls": ["https://state.gov.in/deputy-cm"],
    }
    assert _validate_candidate("Example State", result, evidence, min_confidence=0.84) is None


def test_validator_rejects_name_not_present_in_evidence():
    evidence = [_official("Ravi Sen is the current Chief Minister of Example State.")]
    result = {
        "state": "Example State",
        "chief_minister": "Asha Rao",
        "confidence": 0.99,
        "status": "verified",
        "evidence_urls": ["https://state.gov.in/cm"],
    }
    assert _validate_candidate("Example State", result, evidence, min_confidence=0.84) is None


def test_recent_marker_is_returned_without_internal_marker():
    now = datetime.now(timezone.utc).isoformat()
    hit = SimpleNamespace(
        answer=f"<!--{CM_SNAPSHOT_MARKER}|as_of={now}|confidence=0.900-->\nVerified answer"
    )
    assert extract_recent_cm_snapshot([hit], max_age_hours=6) == "Verified answer"


def test_stale_marker_is_not_used():
    old = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()
    hit = SimpleNamespace(
        answer=f"<!--{CM_SNAPSHOT_MARKER}|as_of={old}|confidence=0.900-->\nOld answer"
    )
    assert extract_recent_cm_snapshot([hit], max_age_hours=6) is None


def test_production_chat_disables_generic_memory_for_live_facts():
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    main = (backend / "app" / "main.py").read_text(encoding="utf-8")
    live = (backend / "app" / "v49" / "live_knowledge.py").read_text(encoding="utf-8")

    assert "extract_recent_cm_snapshot" in main
    assert "and not needs_live_web(query)" in main
    assert "VASUKI_V49_1_AUTHORITATIVE_CURRENT_FACTS" in live
