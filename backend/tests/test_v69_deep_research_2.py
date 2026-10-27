from pathlib import Path

from app.v69.deep_research import health_snapshot, normalize_plan


def test_v69_plan_is_editable_and_deduplicated():
    plan = normalize_plan(
        "research AI agents",
        {
            "objective": "Compare current AI agents",
            "subquestions": [
                {"question": "What can browser agents do?", "requires_current": True},
                {"question": "What can browser agents do?", "requires_current": True},
                {"question": "What safety approvals exist?", "requires_current": True},
            ],
            "conflicts_to_check": ["Conflicting capability claims"],
        },
    )
    assert plan["editable"] is True
    assert len(plan["subquestions"]) == 2
    assert plan["subquestions"][0]["id"] == "q1"
    assert plan["subquestions"][1]["id"] == "q2"


def test_v69_never_claims_source_free_research():
    health = health_snapshot()
    assert health["ok"] is True
    assert health["version"] == "v69"
    assert health["safety"]["fake_sources_allowed"] is False
    assert health["safety"]["factual_report_without_sources_allowed"] is False
    assert health["safety"]["user_edits_plan_before_execution"] is True


def test_v69_production_backend_wiring_present():
    repo = Path(__file__).resolve().parents[2]
    main_v11 = (repo / "backend/app/main_v11.py").read_text(encoding="utf-8")
    assert '"/health/v69"' in main_v11
    assert '"/api/v69/research/plan"' in main_v11
    assert '"/api/v69/research/run"' in main_v11
    assert "v69_create_research_job" in main_v11
    assert "v69_shutdown_research_jobs" in main_v11


def test_v69_frontend_has_real_plan_review_and_job_flow():
    repo = Path(__file__).resolve().parents[2]
    api = (repo / "frontend/lib/api.ts").read_text(encoding="utf-8")
    chat = (repo / "frontend/components/ChatApp.tsx").read_text(encoding="utf-8")
    css = (repo / "frontend/app/globals.css").read_text(encoding="utf-8")

    assert "createDeepResearchPlanV69" in api
    assert "startDeepResearchV69" in api
    assert "fetchDeepResearchV69" in api
    assert "cancelDeepResearchV69" in api
    assert "ResearchPlanModalV69" in chat
    assert "reviewResearchPlanV69" in chat
    assert 'mode === "research"' in chat
    assert "pv-research-plan-backdrop" in css
