from app.v49.current_facts import (
    _candidate_names_from_item,
    _deterministic_fact,
    _role_window_supports,
)


def _uk_source():
    return {
        "title": "VC | Chief Minister, Government of Uttarakhand | India",
        "content": (
            "# Hon’ble Chief Minister’s Biography\n"
            "Image: PS_DHAMI\n"
            "## Shri Pushkar Singh Dhami\n"
            "### Honorable Chief Minister\n"
            "Shri Pushkar Singh Dhami\n"
            "Date Of Birth | 16 September 1975"
        ),
        "source_type": "official",
        "url": "https://cm.uk.gov.in/about-chief-minister/",
        "entity": "Uttarakhand",
        "published_date": "2026-08-29",
    }


def test_uttarakhand_official_markdown_extracts_name():
    assert _candidate_names_from_item(_uk_source()) == ["Pushkar Singh Dhami"]


def test_uttarakhand_official_markdown_supports_role():
    assert _role_window_supports("Pushkar Singh Dhami", _uk_source()) is True


def test_uttarakhand_official_source_resolves_deterministically():
    fact = _deterministic_fact(
        "Uttarakhand",
        [_uk_source()],
        min_confidence=0.84,
    )
    assert fact is not None
    assert fact.chief_minister == "Pushkar Singh Dhami"


def test_deputy_still_fails_closed():
    item = {
        "title": "Deputy Chief Minister",
        "content": "Asha Rao is the Deputy Chief Minister of Example State.",
        "source_type": "official",
        "url": "https://state.gov.in/cm",
        "entity": "Example State",
        "published_date": "2026-08-29",
    }
    assert _candidate_names_from_item(item) == []
    assert _role_window_supports("Asha Rao", item) is False


def test_marker_present():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "app" / "v49" / "current_facts.py"
    assert "VASUKI_V49_2_3_OFFICIAL_CM_MARKUP_FIX" in path.read_text(encoding="utf-8")
