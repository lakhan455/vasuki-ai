from app.v49.current_facts import (
    _candidate_names_from_item,
    _deterministic_fact,
    _role_window_supports,
)


def _item(title, content, source_type="official", url="https://example.gov.in/cm"):
    return {
        "title": title,
        "content": content,
        "source_type": source_type,
        "url": url,
        "entity": "Example State",
        "published_date": "2026-08-29",
    }


def test_honorific_extracts_exact_name():
    assert _candidate_names_from_item(
        _item(
            "CM Office",
            "Hon'ble Chief Minister Shri Asha Rao addressed the meeting today.",
        )
    ) == ["Asha Rao"]


def test_cm_abbreviation_extracts_exact_name():
    assert _candidate_names_from_item(
        _item(
            "Official Portal",
            "CM Asha Rao chaired the cabinet meeting.",
        )
    ) == ["Asha Rao"]


def test_initials_name():
    assert _candidate_names_from_item(
        _item(
            "Chief Minister",
            "D. K. Shivakumar is the current Chief Minister of Example State.",
        )
    ) == ["D. K. Shivakumar"]


def test_single_word_name():
    assert _candidate_names_from_item(
        _item(
            "Chief Minister",
            "Lalduhoma is the current Chief Minister of Example State.",
        )
    ) == ["Lalduhoma"]


def test_deputy_cm_is_rejected():
    source = _item(
        "Deputy Chief Minister",
        "Asha Rao is the Deputy Chief Minister of Example State.",
    )
    assert _candidate_names_from_item(source) == []
    assert _role_window_supports("Asha Rao", source) is False


def test_official_source_resolves_without_chat_provider():
    source = _item(
        "Chief Minister",
        "Asha Rao is the current Chief Minister of Example State.",
    )
    fact = _deterministic_fact(
        "Example State",
        [source],
        min_confidence=0.84,
    )
    assert fact is not None
    assert fact.chief_minister == "Asha Rao"
    assert fact.confidence >= 0.95


def test_v49_1_6_marker():
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "v49"
        / "current_facts.py"
    )
    text = path.read_text(encoding="utf-8")
    assert "VASUKI_V49_1_6_AST_SAFE_FINAL_FIX" in text
