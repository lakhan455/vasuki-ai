from app.v49.current_facts import (
    _candidate_names_from_item,
    _deterministic_fact,
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


def test_honble_is_not_a_candidate():
    candidates = _candidate_names_from_item(_uk_source())
    assert "Hon’ble" not in candidates
    assert candidates == ["Pushkar Singh Dhami"]


def test_uttarakhand_resolves_deterministically():
    fact = _deterministic_fact(
        "Uttarakhand",
        [_uk_source()],
        min_confidence=0.84,
    )
    assert fact is not None
    assert fact.chief_minister == "Pushkar Singh Dhami"


def test_marker_present():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "app" / "v49" / "current_facts.py"
    assert "VASUKI_V49_2_4_HONORIFIC_FILTER_FIX" in path.read_text(encoding="utf-8")
