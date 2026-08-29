import app.v49.current_facts as cf


def _source(url, source_type, candidates):
    return {
        "url": url,
        "title": "Source",
        "content": "Chief Minister evidence",
        "source_type": source_type,
        "published_date": "2026-08-24",
        "_test_candidates": candidates,
    }


def _run_case(monkeypatch, state, full_name, short_name, junk):
    rows = [
        _source(
            f"https://cm.{state.lower().replace(' ', '')}.gov.in/profile",
            "official",
            [full_name, short_name, junk],
        ),
        _source(
            "https://trusted.example.com/a",
            "reputable_news",
            [full_name, short_name],
        ),
        _source(
            "https://trusted2.example.com/b",
            "trusted_reference",
            [full_name],
        ),
    ]

    monkeypatch.setattr(
        cf,
        "_candidate_names_from_item",
        lambda item: item["_test_candidates"],
    )

    def positive(name, evidence):
        if name == full_name:
            return [rows[0], rows[1], rows[2]]
        if name == short_name:
            return [rows[0], rows[1]]
        if name == junk:
            return [rows[0]]
        return []

    monkeypatch.setattr(cf, "_positive_evidence", positive)

    fact = cf._deterministic_fact(
        state,
        rows,
        min_confidence=0.84,
    )

    assert fact is not None
    assert fact.chief_minister == full_name


def test_pushkar_alias_and_tenure_junk(monkeypatch):
    _run_case(
        monkeypatch,
        "Uttarakhand",
        "Pushkar Singh Dhami",
        "Dhami",
        "Tenure",
    )


def test_punjab_alias_and_designation_junk(monkeypatch):
    _run_case(
        monkeypatch,
        "Punjab",
        "Bhagwant Mann",
        "Mann",
        "Designation",
    )


def test_tripura_alias_and_homepage_junk(monkeypatch):
    _run_case(
        monkeypatch,
        "Tripura",
        "Manik Saha",
        "Saha",
        "Homepage",
    )


def test_west_bengal_alias_and_press_junk(monkeypatch):
    _run_case(
        monkeypatch,
        "West Bengal",
        "Suvendu Adhikari",
        "Adhikari",
        "Press Releases",
    )


def test_single_word_real_name_is_preserved(monkeypatch):
    row = _source(
        "https://cm.example.gov.in/profile",
        "official",
        ["Lalduhoma"],
    )

    monkeypatch.setattr(
        cf,
        "_candidate_names_from_item",
        lambda item: item["_test_candidates"],
    )
    monkeypatch.setattr(
        cf,
        "_positive_evidence",
        lambda name, evidence: [row] if name == "Lalduhoma" else [],
    )

    fact = cf._deterministic_fact(
        "Mizoram",
        [row],
        min_confidence=0.84,
    )

    assert fact is not None
    assert fact.chief_minister == "Lalduhoma"


def test_marker_present():
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "v49"
        / "current_facts.py"
    )
    assert "VASUKI_V49_2_6_CANDIDATE_QUALITY_GUARD_FIX" in path.read_text(
        encoding="utf-8"
    )
