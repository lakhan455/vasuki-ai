from __future__ import annotations

import re
from typing import Any


RISKY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bdeploy\b", "deployment"),
    (r"\brelease\b", "release"),
    (r"\bmerge\b", "repository-write"),
    (r"\bdelete\b", "destructive-delete"),
    (r"\bremove\s+production\b", "destructive-delete"),
    (r"\bpayment\b", "financial-action"),
    (r"\bpay\b", "financial-action"),
    (r"\bpurchase\b", "financial-action"),
    (r"\bbuy\b", "financial-action"),
    (r"\bsend\s+(?:an?\s+)?email\b", "external-communication"),
    (r"\bemail\s+.*\bsend\b", "external-communication"),
    (r"\bpublish\b", "external-publication"),
    (r"\bpost\s+(?:it\s+)?(?:online|publicly)\b", "external-publication"),
)


def _clean_goal(goal: str) -> str:
    return re.sub(r"\s+", " ", str(goal or "")).strip()


def risk_snapshot(goal: str) -> dict[str, Any]:
    value = _clean_goal(goal)
    lowered = value.casefold()

    reasons: list[str] = []

    for pattern, reason in RISKY_PATTERNS:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            if reason not in reasons:
                reasons.append(reason)

    return {
        "level": "high" if reasons else "low",
        "approval_required": bool(reasons),
        "reasons": reasons,
    }


def goal_mode(goal: str, *, project_id: str | None = None) -> str:
    text = _clean_goal(goal).casefold()

    if any(
        token in text
        for token in (
            "research",
            "search",
            "find latest",
            "latest information",
            "compare sources",
            "verify online",
        )
    ):
        return "research"

    if re.search(r"\d+\s*[\+\-\*/%]\s*\d+", text):
        return "calculator"

    if (
        project_id
        and any(
            token in text
            for token in (
                "code",
                "fix",
                "bug",
                "repository",
                "repo",
                "project",
                "website",
                "app",
                "backend",
                "frontend",
                "test",
            )
        )
    ):
        return "project-work"

    return "direct-work"


def build_autonomous_plan(
    goal: str,
    *,
    project_id: str | None = None,
) -> dict[str, Any]:
    value = _clean_goal(goal)

    if len(value) < 3:
        raise ValueError("Goal is too short.")

    mode = goal_mode(
        value,
        project_id=project_id,
    )

    risk = risk_snapshot(value)

    steps: list[dict[str, Any]] = [
        {
            "id": "understand",
            "stage": "understand",
            "description": "Understand the requested outcome and constraints.",
            "automatic": True,
        },
        {
            "id": "plan",
            "stage": "plan",
            "description": "Build the smallest safe execution plan.",
            "automatic": True,
        },
    ]

    if mode == "research":
        steps.append(
            {
                "id": "execute",
                "stage": "execute",
                "description": "Collect live evidence and produce a grounded result.",
                "automatic": True,
            }
        )
    elif mode == "calculator":
        steps.append(
            {
                "id": "execute",
                "stage": "execute",
                "description": "Run deterministic calculation.",
                "automatic": True,
            }
        )
    elif mode == "project-work":
        steps.append(
            {
                "id": "execute",
                "stage": "execute",
                "description": "Inspect project context and prepare safe project work.",
                "automatic": True,
            }
        )
    else:
        steps.append(
            {
                "id": "execute",
                "stage": "execute",
                "description": "Produce the requested work using the available intelligence route.",
                "automatic": True,
            }
        )

    steps.extend(
        [
            {
                "id": "verify",
                "stage": "verify",
                "description": "Verify execution evidence before claiming completion.",
                "automatic": True,
            },
            {
                "id": "retry",
                "stage": "retry",
                "description": "Retry failed or blocked work only when it is safe to do so.",
                "automatic": not risk["approval_required"],
            },
            {
                "id": "complete",
                "stage": "complete",
                "description": "Return the verified result and preserve useful context.",
                "automatic": True,
            },
        ]
    )

    return {
        "ok": True,
        "version": "v81",
        "engine": "Vasuki Autonomous Core",
        "goal": value,
        "project_id": str(project_id or "").strip() or None,
        "mode": mode,
        "risk": risk,
        "steps": steps,
        "execution_engine": "v68-real-work-mode",
        "approval_engine": "v77-scoped-approval",
        "memory_layer": "v74-v79",
        "provider_policy": {
            "single_provider_required": False,
            "fallback_supported": True,
            "local_deterministic_routing": True,
        },
    }


def verify_work_snapshot(
    job: dict[str, Any],
) -> dict[str, Any]:
    status = str(job.get("status") or "unknown")
    events = job.get("events")
    events = events if isinstance(events, list) else []

    result = job.get("result")
    pending = job.get("pending_action")

    terminal = status in {
        "succeeded",
        "blocked",
        "failed",
        "cancelled",
    }

    verified_complete = (
        status == "succeeded"
        and isinstance(result, dict)
    )

    retry_allowed = (
        status in {"failed", "blocked", "cancelled"}
        and pending is None
    )

    if verified_complete:
        verdict = "verified-complete"
    elif status == "awaiting_approval":
        verdict = "awaiting-user-approval"
    elif status in {"failed", "blocked"}:
        verdict = "needs-recovery"
    elif status == "cancelled":
        verdict = "cancelled"
    elif status in {"queued", "running"}:
        verdict = "in-progress"
    else:
        verdict = "unverified"

    return {
        "status": status,
        "terminal": terminal,
        "verified_complete": verified_complete,
        "verdict": verdict,
        "retry_allowed": retry_allowed,
        "evidence_events": len(events),
        "pending_approval": status == "awaiting_approval",
        "no_fake_completion": True,
    }


def health_snapshot() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v81",
        "name": "Vasuki Autonomous Core",
        "loop": [
            "goal",
            "plan",
            "execute",
            "verify",
            "retry",
            "complete",
        ],
        "execution": {
            "reuses_v68_real_work_mode": True,
            "reuses_v77_approval_engine": True,
            "reuses_v74_v79_memory": True,
            "provider_fallback_preserved": True,
            "single_provider_dependency": False,
        },
        "safety": {
            "risky_external_actions_auto_execute": False,
            "project_writes_keep_existing_approval": True,
            "fake_completion_claims": False,
            "retry_terminal_failures_only": True,
        },
        "ui_changes_required": False,
        "new_database_migration_required": False,
    }
