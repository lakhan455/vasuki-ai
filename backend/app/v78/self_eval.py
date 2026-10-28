from __future__ import annotations

import time
from threading import Lock
from typing import Any

from app.v11.quality import run_eval

FIXED_EVAL_CASES = 400
DEFAULT_MIN_SCORE = 60.0
DEFAULT_MIN_CATEGORY_SCORE = 50.0
REGRESSION_SUITES: dict[str, list[str]] = {
    "browser-project": [
        "tests/test_v70_real_browser_agent.py",
        "tests/test_v71_project_brain_3.py",
    ],
    "data-agents": [
        "tests/test_v72_data_analyst.py",
        "tests/test_v73_multi_agent.py",
    ],
    "memory-automation": [
        "tests/test_v74_memory3.py",
        "tests/test_v75_autonomous_tasks.py",
    ],
    "workspace-security": [
        "tests/test_v76_live_workspace.py",
        "tests/test_v77_approval_engine.py",
    ],
}

_LOCK = Lock()
_LAST_SUMMARY: dict[str, Any] | None = None


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def assess_report(
    report: dict[str, Any],
    *,
    min_score: float = DEFAULT_MIN_SCORE,
    min_category_score: float = DEFAULT_MIN_CATEGORY_SCORE,
    expected_case_count: int = FIXED_EVAL_CASES,
) -> dict[str, Any]:
    overall = _number(report.get("score"))
    case_count = int(report.get("case_count") or 0)
    category_scores = report.get("category_scores")
    if not isinstance(category_scores, dict):
        category_scores = {}

    weak_categories = {
        str(name): round(_number(score), 2)
        for name, score in category_scores.items()
        if _number(score) < float(min_category_score)
    }
    complete = case_count == int(expected_case_count)
    score_ok = overall >= float(min_score)
    categories_ok = not weak_categories
    passed = bool(complete and score_ok and categories_ok)

    reasons: list[str] = []
    if not complete:
        reasons.append(
            f"expected {expected_case_count} eval cases, received {case_count}"
        )
    if not score_ok:
        reasons.append(
            f"overall score {overall:.2f} is below {float(min_score):.2f}"
        )
    if weak_categories:
        names = ", ".join(sorted(weak_categories))
        reasons.append(
            f"category score below {float(min_category_score):.2f}: {names}"
        )

    return {
        "passed": passed,
        "state": "pass" if passed else "fail",
        "overall_score": round(overall, 2),
        "min_score": float(min_score),
        "min_category_score": float(min_category_score),
        "case_count": case_count,
        "expected_case_count": int(expected_case_count),
        "category_scores": {
            str(name): round(_number(score), 2)
            for name, score in category_scores.items()
        },
        "weak_categories": weak_categories,
        "reasons": reasons,
    }


def _set_last_summary(summary: dict[str, Any]) -> None:
    global _LAST_SUMMARY
    with _LOCK:
        _LAST_SUMMARY = dict(summary)


def last_summary() -> dict[str, Any] | None:
    with _LOCK:
        return dict(_LAST_SUMMARY) if _LAST_SUMMARY is not None else None


async def run_release_eval(
    settings: Any,
    *,
    release: str,
    live: bool = False,
    limit: int = FIXED_EVAL_CASES,
    min_score: float = DEFAULT_MIN_SCORE,
    min_category_score: float = DEFAULT_MIN_CATEGORY_SCORE,
) -> dict[str, Any]:
    bounded_limit = max(1, min(FIXED_EVAL_CASES, int(limit)))
    started = time.perf_counter()
    report = await run_eval(
        settings,
        release=str(release or "v78")[:100],
        live=bool(live),
        limit=bounded_limit,
        concurrency=3,
    )
    gate = assess_report(
        report,
        min_score=min_score,
        min_category_score=min_category_score,
        expected_case_count=bounded_limit,
    )
    summary = {
        "version": "v78",
        "release": str(release or "v78")[:100],
        "mode": "live" if live else "contract",
        "gate": gate,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "run_id": report.get("run_id"),
    }
    _set_last_summary(summary)
    return {
        "ok": gate["passed"],
        "version": "v78",
        "release_gate": gate,
        "eval": report,
        "summary": summary,
    }


def health_snapshot() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v78",
        "name": "Vasuki Self-Evaluation 2.0",
        "features": [
            "fixed-400-case-contract-eval",
            "category-score-release-thresholds",
            "v70-v77-regression-matrix",
            "frontend-lint-and-production-build-gate",
            "security-contract-regressions",
            "github-actions-release-gate",
            "machine-readable-eval-artifact",
            "owner-evaluation-snapshot",
        ],
        "release_gate": {
            "fixed_eval_cases": FIXED_EVAL_CASES,
            "default_min_score": DEFAULT_MIN_SCORE,
            "default_min_category_score": DEFAULT_MIN_CATEGORY_SCORE,
            "regression_suites": REGRESSION_SUITES,
            "fails_ci_on_regression": True,
            "live_model_eval_required_for_every_pr": False,
            "reason_live_eval_optional": "Avoids secret/provider availability making deterministic PR gating flaky.",
        },
        "privacy": {
            "health_snapshot_stores_prompts": False,
            "health_snapshot_stores_answers": False,
            "last_runtime_summary_in_memory_only": True,
        },
        "last_runtime_summary": last_summary(),
        "new_database_migration_required": False,
        "new_api_key_required": False,
    }
