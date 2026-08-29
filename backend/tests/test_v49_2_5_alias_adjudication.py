import app.v49.current_facts as cf


def _source(url, source_type, candidates, published_date="2026-08-24"):
    return {
        "url": url,
        "title": "Source",
        "content": "Chief Minister evidence",
        "source_type": source_type,
        "published_date": published_date,
        "_test_candidates": candidates,
    }


def test_short_aliases_are_consolidated(monkeypatch):
    evidence = [
        _source(
            "https://cm.example.gov.in/profile",
            "official",
            ["Pushkar Singh Dhami", "Dhami", "Tenure"],
        ),
        _source(
            "https://news.example.com/a",
            "reputable_news",
            ["Pushkar Dhami", "Dhami"],
        ),
        _source(
            "https://news2.example.com/b",
            "reputable_news",
            ["Pushkar Singh Dhami"],
        ),
    ]

    monkeypatch.setattr(
        cf,
        "_candidate_names_from_item",
        lambda item: item["_test_candidates"],
    )

    def positive(name, rows):
        mapping = {
            "Pushkar Singh Dhami": [rows[0], rows[2]],
            "Pushkar Dhami": [rows[1]],
            "Dhami": [rows[0], rows[1]],
            "Tenure": [rows[0]],
        }
        return mapping.get(name, [])

    monkeypatch.setattr(cf, "_positive_evidence", positive)

    fact = cf._deterministic_fact(
        "Uttarakhand",
        evidence,
        min_confidence=0.84,
    )

    assert fact is not None
    assert fact.chief_minister == "Pushkar Singh Dhami"


def test_single_word_real_name_still_works(monkeypatch):
    evidence = [
        _source(
            "https://cm.example.gov.in/profile",
            "official",
            ["Lalduhoma"],
        )
    ]

    monkeypatch.setattr(
        cf,
        "_candidate_names_from_item",
        lambda item: item["_test_candidates"],
    )
    monkeypatch.setattr(
        cf,
        "_positive_evidence",
        lambda name, rows: rows if name == "Lalduhoma" else [],
    )

    fact = cf._deterministic_fact(
        "Mizoram",
        evidence,
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
    assert "VASUKI_V49_2_5_ALIAS_ADJUDICATION_FIX" in path.read_text(
        encoding="utf-8"
    )
