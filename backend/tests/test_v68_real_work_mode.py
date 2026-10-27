from pathlib import Path

from app.v68.work_mode import health_snapshot, work_contract


def test_v68_research_contract_is_real():
    contract = work_contract(
        "Research the latest verified AI browser agent trends with sources."
    )
    assert contract["no_fake_execution"] is True
    assert contract["server_side_tests_claimed"] is False


def test_v68_project_code_requires_project_context_or_real_approval_path():
    without_project = work_contract(
        "Fix this React project login bug and update the code."
    )
    with_project = work_contract(
        "Fix this React project login bug and update the code.",
        project_id="project-123",
    )
    if without_project["mode"] == "code_agent":
        assert without_project["support"] == "requires_active_project"
        assert with_project["support"] == "real_project_patch_with_approval"


def test_v68_health_declares_no_fake_tests():
    health = health_snapshot()
    assert health["ok"] is True
    assert health["version"] == "v68"
    assert health["safety"]["project_writes_require_explicit_approval"] is True
    assert health["safety"]["server_side_arbitrary_test_execution"] is False
    assert health["safety"]["fake_execution_claims_allowed"] is False


def test_v68_production_wiring_present():
    repo = Path(__file__).resolve().parents[2]
    main_v11 = (repo / "backend/app/main_v11.py").read_text(encoding="utf-8")
    api = (repo / "frontend/lib/api.ts").read_text(encoding="utf-8")
    chat = (repo / "frontend/components/ChatApp.tsx").read_text(encoding="utf-8")

    assert '"/health/v68"' in main_v11
    assert '"/api/v68/work"' in main_v11
    assert "create_work_job" in main_v11
    assert "startWorkV68" in api
    assert "approveWorkV68" in api
    assert "workMode" in chat
    assert "Chat" in chat and "Work" in chat
