from __future__ import annotations

from pathlib import Path

from app.v78.self_eval import assess_report, health_snapshot


def test_v78_release_gate_passes_complete_healthy_report():
    result = assess_report(
        {
            "score": 82.5,
            "case_count": 400,
            "category_scores": {"chat": 81, "research": 76, "code": 79},
        }
    )
    assert result["passed"] is True
    assert result["state"] == "pass"
    assert result["weak_categories"] == {}


def test_v78_release_gate_fails_missing_cases_or_weak_category():
    result = assess_report(
        {
            "score": 78,
            "case_count": 399,
            "category_scores": {"chat": 80, "research": 42},
        }
    )
    assert result["passed"] is False
    assert result["state"] == "fail"
    assert result["weak_categories"]["research"] == 42.0
    assert len(result["reasons"]) >= 2


def test_v78_health_declares_regression_matrix_and_privacy():
    health = health_snapshot()
    assert health["version"] == "v78"
    assert health["release_gate"]["fixed_eval_cases"] == 400
    suites = health["release_gate"]["regression_suites"]
    assert "browser-project" in suites
    assert "workspace-security" in suites
    assert health["privacy"]["health_snapshot_stores_prompts"] is False
    assert health["new_database_migration_required"] is False


def test_v78_production_wiring_and_ci_present():
    repo = Path(__file__).resolve().parents[2]
    main = (repo / "backend/app/main_v11.py").read_text(encoding="utf-8")
    api = (repo / "frontend/lib/api.ts").read_text(encoding="utf-8")
    owner = (repo / "frontend/app/owner/page.tsx").read_text(encoding="utf-8")
    workflow = (repo / ".github/workflows/v78-self-eval.yml").read_text(encoding="utf-8")
    runner = (repo / "backend/scripts/run_v78_eval.py").read_text(encoding="utf-8")

    assert '"/health/v78"' in main
    assert '"/api/owner/v78/self-evaluation"' in main
    assert '"/api/owner/v78/evals/run"' in main
    assert "fetchOwnerSelfEvaluationV78" in api
    assert "V78 Self-Evaluation" in owner
    assert "test_v77_approval_engine.py" in workflow
    assert "run_v78_eval.py" in workflow
    assert "run_release_eval" in runner
