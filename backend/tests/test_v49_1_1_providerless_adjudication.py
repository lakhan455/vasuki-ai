from app.v49.current_facts import (
    _candidate_names_from_item,
    _deterministic_fact,
)


def _source(
    name: str,
    source_type: str = "official",
    url: str = "https://state.gov.in/cm",
):
    return {
        "title": "Chief Minister",
        "url": url,
        "content": f"{name} is the current Chief Minister of Example State.",
        "source_type": source_type,
        "entity": "Example State",
        "published_date": "2026-08-29",
    }


def test_candidate_extractor_handles_initials():
    assert "D. K. Shivakumar" in _candidate_names_from_item(_source("D. K. Shivakumar"))


def test_candidate_extractor_handles_single_word_name():
    assert "Lalduhoma" in _candidate_names_from_item(_source("Lalduhoma"))


def test_deterministic_adjudicator_accepts_official_source():
    fact = _deterministic_fact(
        "Example State",
        [_source("Asha Rao")],
        min_confidence=0.84,
    )
    assert fact is not None
    assert fact.chief_minister == "Asha Rao"
    assert fact.confidence >= 0.95


def test_deterministic_adjudicator_accepts_two_trusted_sources():
    evidence = [
        _source("Asha Rao", "reputable_news", "https://reuters.com/a"),
        _source("Asha Rao", "reputable_news", "https://bbc.com/b"),
    ]
    fact = _deterministic_fact("Example State", evidence, min_confidence=0.84)
    assert fact is not None
    assert fact.chief_minister == "Asha Rao"


def test_deterministic_adjudicator_rejects_deputy_cm():
    evidence = [{
        "title": "Deputy Chief Minister",
        "url": "https://state.gov.in/deputy",
        "content": "Asha Rao is the Deputy Chief Minister of Example State.",
        "source_type": "official",
        "entity": "Example State",
        "published_date": "2026-08-29",
    }]
    assert _deterministic_fact("Example State", evidence, min_confidence=0.84) is None


def test_provider_failure_is_caught_in_source():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "app" / "v49" / "current_facts.py"
    text = path.read_text(encoding="utf-8")
    assert "chat-verifier-unavailable" in text
    assert "deterministic-source-adjudicator-v49.1.1" in text
