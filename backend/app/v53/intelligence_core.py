from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.v13.orchestrator import orchestrate_request
from app.v20.planner import build_execution_plan_v20


@dataclass(frozen=True, slots=True)
class IntelligenceContract:
    version: str
    mode: str
    task_type: str
    difficulty: str
    confidence: float
    verification_required: bool
    activity: str
    objective: str
    steps: tuple[str, ...]
    context: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = list(self.steps)
        return data


def _mode(task_type: str, primary_action: str) -> str:
    if primary_action == "code_agent" or task_type == "code":
        return "engineering"
    if primary_action == "research" or task_type == "research":
        return "verified-research"
    if task_type == "reasoning":
        return "deep-reasoning"
    if primary_action == "artifact":
        return "artifact"
    if primary_action == "image":
        return "image"
    return "direct"


def _activity(mode: str, *, project_active: bool, verification: bool) -> str:
    if mode == "engineering":
        return "Inspecting project…" if project_active else "Planning code…"
    if mode == "verified-research":
        return "Checking sources…"
    if mode == "deep-reasoning":
        return "Reasoning…"
    if verification:
        return "Verifying answer…"
    return "Preparing answer…"


def build_intelligence_contract(
    messages: list[dict[str, Any]],
    *,
    require_current: bool = False,
    project_active: bool = False,
    evidence_confidence: float | None = None,
) -> IntelligenceContract:
    decision = orchestrate_request(messages, require_current=require_current)
    plan = build_execution_plan_v20(messages, project_active=project_active)

    mode = _mode(
        decision.intelligence.task_type,
        decision.primary_action,
    )
    verification = bool(
        decision.verify_after
        or decision.intelligence.needs_verification
        or require_current
    )

    confidence = float(decision.intelligence.confidence)
    if verification and evidence_confidence is not None:
        evidence = max(0.0, min(1.0, float(evidence_confidence)))
        confidence = confidence * 0.68 + evidence * 0.32
    if project_active and mode == "engineering":
        confidence += 0.03
    confidence = round(max(0.20, min(0.98, confidence)), 3)

    objective = str(plan.objective or "").strip()[:1200]
    steps = tuple(
        f"{item.step}: {item.purpose}"
        for item in plan.steps
    )

    context_lines = [
        "VASUKI V53 INTELLIGENCE CONTRACT:",
        (
            f"Mode={mode}; task={decision.intelligence.task_type}; "
            f"difficulty={decision.intelligence.difficulty}."
        ),
        f"Objective: {objective or 'Answer the latest user request completely.'}",
        "Internal plan: " + " | ".join(steps),
        (
            "Return only the useful final answer, not hidden chain-of-thought "
            "or private reasoning."
        ),
        (
            "Satisfy the user's explicit constraints before adding optional detail."
        ),
        (
            "Do not claim that a tool, test, deployment, file change, or external "
            "action happened unless the supplied context proves it."
        ),
    ]

    if verification:
        context_lines.extend([
            (
                "Verification is required: distinguish verified facts from inference."
            ),
            (
                "If supplied evidence conflicts, say so and resolve it using the "
                "strongest and freshest evidence instead of silently guessing."
            ),
        ])

    if mode == "engineering":
        context_lines.extend([
            (
                "For code: inspect supplied project evidence first, preserve interfaces "
                "unless a change is necessary, and include the smallest useful "
                "regression-test plan."
            ),
            (
                "Never claim tests passed unless actual test output is present "
                "in the context."
            ),
        ])

    if mode == "verified-research":
        context_lines.append(
            (
                "For research: synthesize across sources, prioritize primary/official "
                "evidence, and do not invent citations."
            )
        )

    return IntelligenceContract(
        version="v53",
        mode=mode,
        task_type=decision.intelligence.task_type,
        difficulty=decision.intelligence.difficulty,
        confidence=confidence,
        verification_required=verification,
        activity=_activity(
            mode,
            project_active=project_active,
            verification=verification,
        ),
        objective=objective,
        steps=steps,
        context="\n".join(context_lines),
    )


def health_snapshot() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v53",
        "name": "Vasuki Intelligence Core",
        "features": [
            "intent-aware-production-chat",
            "planner-to-answer-contract",
            "confidence-calibration",
            "verification-policy",
            "task-aware-activity-state",
            "no-hidden-chain-of-thought-exposure",
        ],
        "extra_provider_call_required_for_simple_chat": False,
        "new_database_migration_required": False,
        "new_api_key_required": False,
    }
