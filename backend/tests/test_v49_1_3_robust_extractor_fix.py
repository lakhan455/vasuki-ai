from app.v49.current_facts import (
    _candidate_names_from_item,
    _deterministic_fact,
    _role_window_supports,
)


def _item(
    *,
    title: str,
    content: str,
    source_type: str = "official",
    url: str = "https://example.gov.in/cm",
):
    return {
        "title": title,
        "content": content,
        "source_type": source_type,
        "url": url,
        "entity": "Example State",
        "published_date": "2026-08-29",
    }


def test_initials_name_extracted_without_heading_bleed():
    item = _item(
        title="Chief Minister",
        content=(
            "D. K. Shivakumar is the current Chief Minister "
            "of Example State."
        ),
    )
    assert "D. K. Shivakumar" in _candidate_names_from_item(item)


def test_single_word_name_extracted():
    item = _item(
        title="Chief Minister",
        content="Lalduhoma is the current Chief Minister of Example State.",
    )
    assert "Lalduhoma" in _candidate_names_from_item(item)


def test_honorific_role_before_name():
    item = _item(
        title="CM Office",
        content=(
            "Hon'ble Chief Minister Shri Asha Rao addressed "
            "the meeting today."
        ),
    )
    assert "Asha Rao" in _candidate_names_from_item(item)


def test_cm_abbreviation_role_before_name():
    item = _item(
        title="Official Portal",
        content="CM Asha Rao chaired the cabinet meeting.",
    )
    assert "Asha Rao" in _candidate_names_from_item(item)


def test_deputy_cm_is_not_promoted():
    item = _item(
        title="Deputy Chief Minister",
        content="Asha Rao is the Deputy Chief Minister of Example State.",
    )
    assert "Asha Rao" not in _candidate_names_from_item(item)
    assert _role_window_supports("Asha Rao", item) is False


def test_valid_cm_not_poisoned_by_nearby_deputy_text():
    item = _item(
        title="Council of Ministers",
        content=(
            "Asha Rao is the current Chief Minister of Example State. "
            "The Deputy Chief Minister is Ravi Sen."
        ),
    )
    assert _role_window_supports("Asha Rao", item) is True


def test_official_source_resolves_without_chat_provider():
    item = _item(
        title="Chief Minister",
        content="Asha Rao is the current Chief Minister of Example State.",
    )
    fact = _deterministic_fact(
        "Example State",
        [item],
        min_confidence=0.84,
    )
    assert fact is not None
    assert fact.chief_minister == "Asha Rao"
    assert fact.confidence >= 0.95


def test_two_independent_trusted_sources_resolve():
    evidence = [
        _item(
            title="Current CM",
            content="Asha Rao is the current Chief Minister of Example State.",
            source_type="reputable_news",
            url="https://reuters.com/a",
        ),
        _item(
            title="State leadership",
            content="Asha Rao serves as the Chief Minister of Example State.",
            source_type="reputable_news",
            url="https://bbc.com/b",
        ),
    ]
    fact = _deterministic_fact(
        "Example State",
        evidence,
        min_confidence=0.84,
    )
    assert fact is not None
    assert fact.chief_minister == "Asha Rao"


def test_patch_marker_present():
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "v49"
        / "current_facts.py"
    )
    text = path.read_text(encoding="utf-8")
    assert "VASUKI_V49_1_3_ROBUST_EXTRACTOR_FIX" in text
