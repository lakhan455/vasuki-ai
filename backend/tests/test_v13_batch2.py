from app.v13.analytics import provider_health_summary
from app.v13.autonomy import build_execution_plan
from app.v13.critic import critic_review
from app.v13.incidents import classify_incident, recovery_plan
from app.v13.orchestrator import orchestrate_request
from app.v13.project_brain import project_snapshot


def test_orchestrator_routes_current_request_to_research():
    decision = orchestrate_request([
        {"role": "user", "content": "Compare the latest current Gemini API pricing today with sources."}
    ])
    assert decision.primary_action == "research"
    assert "web.search" in decision.tools
    assert decision.verify_after is True


def test_orchestrator_requires_confirmation_for_production_write():
    decision = orchestrate_request([
        {"role": "user", "content": "Deploy to production and push to main."}
    ])
    assert decision.confirmation_required is True


def test_execution_plan_builds_code_repair_and_test_chain():
    plan = build_execution_plan([
        {"role": "user", "content": "Fix this FastAPI project traceback, repair the code and test everything."}
    ])
    actions = [step.action for step in plan.steps]
    assert plan.mode == "code_agent"
    assert any("repair" in action for action in actions)
    assert any("regression" in action for action in actions)


def test_critic_flags_unsupported_current_answer():
    result = critic_review(
        "What is the latest price today?",
        "The current price is $99 in 2026.",
        sources=[],
        current_required=True,
    )
    assert result.needs_repair is True
    assert result.score < 80
    assert result.repair_instruction


def test_incident_recovery_switches_on_quota():
    assert classify_incident("429 RESOURCE_EXHAUSTED quota depleted") in {"quota", "rate_limit"}
    plan = recovery_plan("gemini", "RESOURCE_EXHAUSTED quota depleted", ["gemini", "groq", "cerebras"])
    assert plan.retry_same_provider is False
    assert plan.switch_provider is True
    assert plan.suggested_provider == "groq"


def test_incident_moderation_is_not_auto_bypassed():
    plan = recovery_plan("cloudflare", "output has been flagged by safety policy", ["huggingface"])
    assert plan.incident_type == "moderation"
    assert plan.switch_provider is False
    assert plan.safe_to_auto_retry is False


def test_project_brain_prioritizes_blockers():
    snapshot = project_snapshot([
        {"title": "UI polish", "status": "pending"},
        {"title": "Provider auth broken", "status": "blocked"},
        {"title": "Backend tests", "status": "testing"},
        {"title": "Old bug", "status": "done"},
    ])
    assert snapshot["counts"]["blocked"] == 1
    assert snapshot["next_actions"][0]["status"] == "blocked"
    assert snapshot["completion_pct"] == 25.0


def test_provider_health_summary_selects_best():
    snap = {
        "groq": {
            "configured": True,
            "tasks": {
                "general": {"score": 0.91, "success_rate": 0.99, "speed": 0.9},
            },
        },
        "gemini": {
            "configured": True,
            "tasks": {
                "general": {"score": 0.82, "success_rate": 0.95, "speed": 0.7},
            },
        },
    }
    summary = provider_health_summary(snap)
    assert summary["best_by_task"]["general"]["provider"] == "groq"
    assert summary["configured_count"] == 2
