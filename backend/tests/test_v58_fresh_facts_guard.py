from pathlib import Path

from app.services.research import needs_live_web
from app.v58.fresh_facts import (
    build_fresh_fact_search_query,
    fresh_fact_answer_policy,
    is_volatile_person_status_query,
)


def test_v58_roman_hindi_death_query_requires_live_web():
    query = "Nana Patekar death kab hui kaise hui"
    assert is_volatile_person_status_query(query) is True
    assert needs_live_web(query) is True


def test_v58_hindi_death_query_requires_live_web():
    query = "नाना पाटेकर की मृत्यु कब हुई और कैसे हुई"
    assert is_volatile_person_status_query(query) is True
    assert needs_live_web(query) is True


def test_v58_alive_query_requires_live_web():
    assert needs_live_web("Is this actor still alive?") is True
    assert needs_live_web("kya ye actor abhi zinda hai") is True


def test_v58_other_volatile_status_queries_require_live_web():
    samples = [
        "when did the CEO resign",
        "was the minister arrested",
        "actor hospitalized latest health condition",
        "when did the player retire",
        "is the politician released from custody",
    ]
    for query in samples:
        assert needs_live_web(query) is True


def test_v58_search_query_blocks_alive_from_absence_inference():
    value = build_fresh_fact_search_query(
        "Nana Patekar death kab hui",
        as_of="2026-10-26",
    )
    assert "Do not infer that a person is alive" in value
    assert "confirmed death reports" in value


def test_v58_answer_policy_is_fail_closed():
    value = fresh_fact_answer_policy(
        "Nana Patekar death kab hui",
        as_of="2026-10-26",
    )
    assert "live evidence" in value
    assert "instead of guessing" in value


def test_v58_is_wired_into_production_sources():
    repo = Path(__file__).resolve().parents[2]

    research = (
        repo / "backend/app/services/research.py"
    ).read_text(encoding="utf-8")

    main = (
        repo / "backend/app/main.py"
    ).read_text(encoding="utf-8")

    main_v5 = (
        repo / "backend/app/main_v5.py"
    ).read_text(encoding="utf-8")

    v54 = (
        repo / "backend/app/v54/knowledge_brain.py"
    ).read_text(encoding="utf-8")

    main_v11 = (
        repo / "backend/app/main_v11.py"
    ).read_text(encoding="utf-8")

    assert "is_volatile_person_status_query" in research
    assert "build_fresh_fact_search_query" in research
    assert "fresh_fact_answer_policy" in main
    assert "fresh_fact_answer_policy" in main_v5
    assert "reputable_news" in v54
    assert '"/health/v58"' in main_v11
