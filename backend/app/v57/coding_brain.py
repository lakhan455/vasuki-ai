from __future__ import annotations

from typing import Any

from app.v13.intelligence import analyze_intent


def build_coding_policy(
    messages: list[dict[str, Any]],
    *,
    project_active: bool,
) -> str:
    plan = analyze_intent(
        messages,
        require_current=False,
    )

    if plan.task_type != "code":
        return ""

    lines = [
        "VASUKI V57 ENGINEERING / SELF-REPAIR CONTRACT:",
        "Inspect supplied repository/project evidence before proposing edits.",
        (
            "Trace dependency impact for definitions, imports, callers, routes, "
            "config, auth boundaries, and relevant tests."
        ),
        (
            "Prefer the smallest compatible patch; do not rewrite unrelated files."
        ),
        (
            "When real test/build output is supplied, diagnose the exact failure "
            "and repair only what the evidence supports."
        ),
        (
            "Never claim that tests, builds, commits, deployments, or file writes "
            "actually happened unless execution evidence is present."
        ),
        (
            "Separate 'validated by supplied output' from 'recommended test to run'."
        ),
        (
            "Preserve secrets, authorization checks, existing user data, and public "
            "interfaces unless the user explicitly requires a migration."
        ),
    ]

    if project_active:
        lines.append(
            (
                "An active project is selected: treat its project memories and "
                "repository files as primary engineering evidence."
            )
        )
    else:
        lines.append(
            (
                "No project repository evidence is selected: clearly mark "
                "file-specific assumptions instead of inventing codebase details."
            )
        )

    if plan.difficulty == "high":
        lines.append(
            (
                "For complex fixes use: inspect -> impact-check -> patch-plan -> "
                "validation-plan -> repair-if-test-output-fails."
            )
        )

    return "\n".join(lines)


def health_snapshot() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v57",
        "name": "Vasuki Engineering Brain",
        "features": [
            "inspect-before-edit-policy",
            "dependency-impact-check",
            "minimal-compatible-patch",
            "regression-test-plan",
            "test-output-driven-repair",
            "no-fake-test-or-deploy-claims",
            "active-project-repository-context",
        ],
        "arbitrary_local_machine_execution": False,
        "new_database_migration_required": False,
        "new_api_key_required": False,
    }
