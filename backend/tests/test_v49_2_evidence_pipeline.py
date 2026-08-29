from app.v49.current_facts import (
    _candidate_names_from_item,
    _deterministic_fact,
    _role_window_supports,
)
from app.services.research import _select_state_evidence


def _src(
    title,
    content,
    source_type="official",
    url="https://state.gov.in/cm",
):
    return {
        "title": title,
        "content": content,
        "source_type": source_type,
        "url": url,
        "entity": "Example State",
        "published_date": "2026-08-29",
        "domain": "state.gov.in",
    }


def test_realistic_official_cm_page_layout():
    item = _src(
        "Chief Minister | Example State",
        "Shri Asha Rao\nWelcome to the official CMO portal.",
    )
    assert _candidate_names_from_item(item) == ["Asha Rao"]
    assert _role_window_supports("Asha Rao", item) is True


def test_realistic_name_before_role():
    item = _src(
        "Latest",
        "D. K. Shivakumar is the current Chief Minister of Example State.",
    )
    assert _candidate_names_from_item(item) == ["D. K. Shivakumar"]


def test_deputy_not_promoted():
    item = _src(
        "Deputy Chief Minister",
        "Asha Rao is the Deputy Chief Minister of Example State.",
    )
    assert _candidate_names_from_item(item) == []
    assert _role_window_supports("Asha Rao", item) is False


def test_evidence_selector_keeps_multiple_sources():
    rows = [
        _src("CM", "Asha Rao is Chief Minister.", "official", f"https://s{i}.gov.in/cm")
        for i in range(3)
    ]
    rows += [
        _src("News", "Asha Rao is Chief Minister.", "reputable_news", f"https://news{i}.com/a")
        for i in range(3)
    ]
    selected = _select_state_evidence(rows)
    assert len(selected) >= 4
    assert sum(1 for x in selected if x["source_type"] == "official") >= 2


def test_official_source_resolves_deterministically():
    item = _src(
        "Chief Minister",
        "Asha Rao is the current Chief Minister of Example State.",
    )
    fact = _deterministic_fact(
        "Example State",
        [item],
        min_confidence=0.84,
    )
    assert fact is not None
    assert fact.chief_minister == "Asha Rao"


def test_v49_2_marker_present():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "app" / "v49" / "current_facts.py"
    assert "VASUKI_V49_2_EVIDENCE_PIPELINE_FIX" in path.read_text(encoding="utf-8")
