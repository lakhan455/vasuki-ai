from app.v49.current_facts import _candidate_names_from_item


def _src(title, content, url="https://state.gov.in/cm"):
    return {
        "title": title,
        "content": content,
        "source_type": "official",
        "url": url,
        "entity": "Example State",
        "published_date": "2026-08-29",
    }


def test_cm_prefix_is_normalized_not_duplicated():
    item = _src(
        "Official Portal",
        "CM Asha Rao chaired the cabinet meeting.",
    )
    assert _candidate_names_from_item(item) == ["Asha Rao"]


def test_newline_name_boundary_still_correct():
    item = _src(
        "Chief Minister | Example State",
        "Shri Asha Rao\nWelcome to the official CMO portal.",
    )
    assert _candidate_names_from_item(item) == ["Asha Rao"]


def test_marker_present():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "app" / "v49" / "current_facts.py"
    assert "VASUKI_V49_2_2_CM_PREFIX_DEDUPE_FIX" in path.read_text(encoding="utf-8")
