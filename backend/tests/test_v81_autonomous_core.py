from app.v81.autonomous_core import (
    build_autonomous_plan,
    health_snapshot,
    risk_snapshot,
    verify_work_snapshot,
)


def test_v81_health_contract():
    health = health_snapshot()

    assert health["ok"] is True
    assert health["version"] == "v81"
    assert health["loop"] == [
        "goal",
        "plan",
        "execute",
        "verify",
        "retry",
        "complete",
    ]
    assert health["execution"]["reuses_v68_real_work_mode"] is True
    assert health["execution"]["reuses_v77_approval_engine"] is True
    assert health["safety"]["risky_external_actions_auto_execute"] is False
    assert health["ui_changes_required"] is False


def test_v81_safe_goal_can_auto_execute():
    plan = build_autonomous_plan(
        "Research current NFC market trends and summarize them."
    )

    assert plan["mode"] == "research"
    assert plan["risk"]["approval_required"] is False
    assert plan["execution_engine"] == "v68-real-work-mode"


def test_v81_project_goal_uses_project_work():
    plan = build_autonomous_plan(
        "Inspect the backend and fix the failing test.",
        project_id="project-123",
    )

    assert plan["mode"] == "project-work"
    assert plan["project_id"] == "project-123"


def test_v81_risky_goal_requires_approval():
    risk = risk_snapshot(
        "Deploy the website and delete the old production release."
    )

    assert risk["level"] == "high"
    assert risk["approval_required"] is True
    assert "deployment" in risk["reasons"]
    assert "destructive-delete" in risk["reasons"]


def test_v81_verifies_completed_work():
    verification = verify_work_snapshot(
        {
            "status": "succeeded",
            "result": {"answer": "done"},
            "events": [{"state": "succeeded"}],
            "pending_action": None,
        }
    )

    assert verification["verified_complete"] is True
    assert verification["verdict"] == "verified-complete"
    assert verification["retry_allowed"] is False


def test_v81_failed_work_can_retry():
    verification = verify_work_snapshot(
        {
            "status": "failed",
            "result": None,
            "events": [{"state": "failed"}],
            "pending_action": None,
        }
    )

    assert verification["verified_complete"] is False
    assert verification["verdict"] == "needs-recovery"
    assert verification["retry_allowed"] is True
