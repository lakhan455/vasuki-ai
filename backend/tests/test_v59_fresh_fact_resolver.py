from pathlib import Path

from app.services.research import needs_live_web
from app.v59.fresh_fact_resolver import (
    build_fresh_fact_plan,
    extract_fresh_fact_subject,
    fresh_fact_evidence_context,
)


def test_v59_extracts_roman_hindi_subject():
    assert extract_fresh_fact_subject(
        "Nana Patekar death kab hui aur kaise hui?"
    ) == "Nana Patekar"


def test_v59_extracts_hindi_subject():
    assert extract_fresh_fact_subject(
        "नाना पाटेकर की मृत्यु कब हुई और कैसे हुई"
    ) == "नाना पाटेकर"


def test_v59_builds_multiple_death_queries():
    plan = build_fresh_fact_plan(
        "Nana Patekar death kab hui aur kaise hui?",
        as_of="2026-10-26",
    )
    assert plan.kind == "death_alive"
    assert plan.subject == "Nana Patekar"
    assert len(plan.queries) >= 3
    joined = " ".join(plan.queries).casefold()
    assert "obituary" in joined
    assert "death hoax" in joined


def test_v59_resolves_confirmed_death_from_two_domains():
    sources = [
        {
            "title": "Indian actor Nana Patekar dies at 75",
            "content": (
                "Nana Patekar died at age 75 at his home in Goa on "
                "October 8, 2026 after a suspected cardiac arrest."
            ),
            "url": "https://apnews.com/example",
            "domain": "apnews.com",
            "source_type": "reputable_news",
            "published_date": "2026-10-08",
        },
        {
            "title": "Nana Patekar dies due to cardiac arrest",
            "content": (
                "His son confirmed the death. Nana Patekar died in Goa "
                "and was cremated with state honours."
            ),
            "url": "https://indianexpress.com/example",
            "domain": "indianexpress.com",
            "source_type": "reputable_news",
            "published_date": "2026-10-09",
        },
    ]
    context = fresh_fact_evidence_context(
        "Nana Patekar death kab hui aur kaise hui?",
        sources,
        as_of="2026-10-26",
    )
    assert "RESOLUTION=CONFIRMED_DECEASED_EVIDENCE" in context
    assert "Do NOT answer that no reliable death evidence exists" in context


def test_v59_does_not_treat_death_hoax_as_confirmed_death():
    sources = [
        {
            "title": "Actor says death rumours are false",
            "content": "The actor is alive and well. The death hoax is false.",
            "url": "https://bbc.com/example",
            "domain": "bbc.com",
            "source_type": "reputable_news",
            "published_date": "2026-10-20",
        },
        {
            "title": "False death report denied",
            "content": "Representatives said he is alive. Reports of death were false.",
            "url": "https://reuters.com/example",
            "domain": "reuters.com",
            "source_type": "reputable_news",
            "published_date": "2026-10-20",
        },
    ]
    context = fresh_fact_evidence_context(
        "is this actor alive?",
        sources,
        as_of="2026-10-26",
    )
    assert "RESOLUTION=EXPLICIT_ALIVE_OR_HOAX_EVIDENCE" in context
    assert "CONFIRMED_DECEASED_EVIDENCE" not in context


def test_v59_keeps_freshness_requirement():
    assert needs_live_web("Nana Patekar death kab hui aur kaise hui?") is True


def test_v59_production_wiring_is_present():
    repo = Path(__file__).resolve().parents[2]

    research = (repo / "backend/app/services/research.py").read_text(encoding="utf-8")
    main = (repo / "backend/app/main.py").read_text(encoding="utf-8")
    main_v4 = (repo / "backend/app/main_v4.py").read_text(encoding="utf-8")
    main_v5 = (repo / "backend/app/main_v5.py").read_text(encoding="utf-8")
    main_v11 = (repo / "backend/app/main_v11.py").read_text(encoding="utf-8")

    assert "build_fresh_fact_plan" in research
    assert "fresh_fact_evidence_context" in main
    assert "fresh_fact_evidence_context" in main_v5
    assert "needs_live_web(query)" in main_v4
    assert '"/health/v59"' in main_v11
