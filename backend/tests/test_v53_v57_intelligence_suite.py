from pathlib import Path

from app.v53.intelligence_core import build_intelligence_contract
from app.v54.knowledge_brain import assess_and_rank_sources
from app.v55.memory_brain import build_smart_memory_context
from app.v57.coding_brain import build_coding_policy


def test_v53_simple_chat_stays_direct():
    contract = build_intelligence_contract(
        [{"role": "user", "content": "hello"}],
    )
    assert contract.mode == "direct"
    assert contract.confidence > 0.5


def test_v53_research_is_verification_aware():
    contract = build_intelligence_contract(
        [
            {
                "role": "user",
                "content": "research the latest RBI policy with sources",
            }
        ],
        require_current=True,
        evidence_confidence=0.9,
    )
    assert contract.mode == "verified-research"
    assert contract.verification_required is True
    assert "Checking sources" in contract.activity


def test_v54_ranks_official_current_source_first():
    pack = assess_and_rank_sources(
        "what is the current repo rate",
        [
            {
                "title": "Blog",
                "url": "https://example.com/blog",
                "domain": "example.com",
                "source_type": "other",
                "content": "Repo rate commentary 6.0%",
            },
            {
                "title": "Official release",
                "url": "https://rbi.example.gov.in/release",
                "domain": "rbi.example.gov.in",
                "source_type": "official",
                "published_date": "2026-10-26",
                "content": "Official current repo rate 6.0%",
            },
        ],
        current_required=True,
    )
    assert pack.sources[0]["source_type"] == "official"
    assert pack.confidence > 0.5


def test_v55_newer_conflicting_memory_suppresses_old():
    context, rows = build_smart_memory_context(
        [
            {
                "memory_text": "Monthly plan price is 199",
                "category": "preference",
                "updated_at": "2026-10-20T10:00:00+00:00",
            },
            {
                "memory_text": "Monthly plan price is 299",
                "category": "preference",
                "updated_at": "2026-10-26T10:00:00+00:00",
            },
        ],
        query="monthly plan price",
    )
    assert "299" in context
    assert "199" not in context
    assert len(rows) == 1


def test_v57_code_policy_never_fakes_execution():
    policy = build_coding_policy(
        [
            {
                "role": "user",
                "content": "fix this FastAPI project bug and run tests",
            }
        ],
        project_active=True,
    )
    assert "Never claim" in policy
    assert "active project" in policy.casefold()


def test_v53_v57_are_wired_into_production_sources():
    repo = Path(__file__).resolve().parents[2]

    main_v5 = (
        repo / "backend/app/main_v5.py"
    ).read_text(encoding="utf-8")

    main = (
        repo / "backend/app/main.py"
    ).read_text(encoding="utf-8")

    api = (
        repo / "frontend/lib/api.ts"
    ).read_text(encoding="utf-8")

    chat = (
        repo / "frontend/components/ChatApp.tsx"
    ).read_text(encoding="utf-8")

    assert "build_intelligence_contract" in main_v5
    assert "critic_review" in main_v5
    assert "assess_and_rank_sources" in main_v5
    assert "build_coding_policy" in main_v5

    assert "project_context_v8" in main
    assert "project_kb_context" in main

    assert "intelligence_confidence" in api
    assert "qualityScore" in chat
