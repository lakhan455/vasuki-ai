from app.v49.current_facts import (
    _candidate_names_from_item,
    _role_window_supports,
)


def _src(title, content, url="https://state.gov.in/cm"):
    return {
        "title": title,
        "content": content,
        "source_type": "official",
        "url": url,
        "entity": "Example State",
        "published_date": "2026-08-29",
    }


def test_newline_terminates_name():
    item = _src(
        "Chief Minister | Example State",
        "Shri Asha Rao\nWelcome to the official CMO portal.",
    )
    assert _candidate_names_from_item(item) == ["Asha Rao"]


def test_deputy_page_not_promoted_by_cm_url():
    item = _src(
        "Deputy Chief Minister",
        "Asha Rao is the Deputy Chief Minister of Example State.",
    )
    assert _candidate_names_from_item(item) == []
    assert _role_window_supports("Asha Rao", item) is False


def test_initials_still_work():
    item = _src(
        "Chief Minister",
        "D. K. Shivakumar is the current Chief Minister of Example State.",
    )
    assert _candidate_names_from_item(item) == ["D. K. Shivakumar"]


def test_single_word_name_still_works():
    item = _src(
        "Chief Minister",
        "Lalduhoma is the current Chief Minister of Example State.",
    )
    assert _candidate_names_from_item(item) == ["Lalduhoma"]


def test_v49_2_1_marker_present():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "app" / "v49" / "current_facts.py"
    text = path.read_text(encoding="utf-8")
    assert "VASUKI_V49_2_1_EXTRACTOR_BOUNDARY_FIX" in text
