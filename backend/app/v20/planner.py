from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.v13.intelligence import analyze_intent
from app.v19.conversation_state import resolve_conversation_state


@dataclass(frozen=True, slots=True)
class PlanStep:
    step: str
    purpose: str
    gate: str


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    version: str
    objective: str
    task_type: str
    difficulty: str
    steps: tuple[PlanStep, ...]
    stop_conditions: tuple[str, ...]
    requires_user_confirmation: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = [asdict(item) for item in self.steps]
        data["stop_conditions"] = list(self.stop_conditions)
        return data


def build_execution_plan_v20(messages: list[dict[str, Any]], *, project_active: bool = False) -> ExecutionPlan:
    state = resolve_conversation_state(messages)
    intent = analyze_intent(messages, require_current=False)
    steps: list[PlanStep] = [
        PlanStep("understand", "Resolve the current user objective and constraints.", "intent resolved"),
    ]

    if project_active and intent.task_type == "code":
        steps.append(PlanStep("inspect", "Inspect only relevant project files and interfaces.", "evidence sufficient"))
    if intent.task_type == "research":
        steps.append(PlanStep("verify", "Gather current/relevant evidence only when web is justified.", "sources relevant"))
    if intent.task_type == "code":
        steps.extend([
            PlanStep("change-plan", "Choose the smallest compatible code change.", "impact understood"),
            PlanStep("validate-plan", "Define regression checks before claiming completion.", "checks identified"),
        ])
    elif intent.task_type == "reasoning":
        steps.append(PlanStep("solve", "Work through the problem with explicit assumptions.", "result internally consistent"))
    else:
        steps.append(PlanStep("answer", "Answer directly without unnecessary tools.", "request satisfied"))

    destructive = any(
        token in state.active_request.casefold()
        for token in ("delete production", "drop table", "deploy now", "push to production", "rotate secret")
    )

    return ExecutionPlan(
        version="v20",
        objective=state.active_request[:1200],
        task_type=intent.task_type,
        difficulty=intent.difficulty,
        steps=tuple(steps),
        stop_conditions=(
            "missing required evidence",
            "permission or confirmation required",
            "unsafe or destructive action requested without approval",
        ),
        requires_user_confirmation=destructive,
    )


def planner_health() -> dict[str, Any]:
    return {
        "version": "v20",
        "name": "Autonomous Planner",
        "features": [
            "objective-to-step-planning",
            "tool-minimization",
            "coding-inspection-gate",
            "validation-before-completion",
            "destructive-action-confirmation-gate",
        ],
        "silent_external_action": False,
        "db_migration_required": False,
        "new_api_key_required": False,
    }
