from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.v13.orchestrator import OrchestrationDecision, orchestrate_request


@dataclass(frozen=True, slots=True)
class ExecutionStep:
    step_id: str
    role: str
    action: str
    tool: str | None
    depends_on: tuple[str, ...]
    critical: bool
    verify: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["depends_on"] = list(self.depends_on)
        return data


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    objective: str
    mode: str
    steps: tuple[ExecutionStep, ...]
    confirmation_required: bool
    parallelizable: bool
    max_repair_attempts: int
    orchestration: OrchestrationDecision

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "mode": self.mode,
            "steps": [step.to_dict() for step in self.steps],
            "confirmation_required": self.confirmation_required,
            "parallelizable": self.parallelizable,
            "max_repair_attempts": self.max_repair_attempts,
            "orchestration": self.orchestration.to_dict(),
        }


def _latest_user_text(messages: list[dict[str, Any]]) -> str:
    return next(
        (
            str(item.get("content") or "").strip()
            for item in reversed(messages)
            if item.get("role") == "user"
        ),
        "",
    )


def build_execution_plan(
    messages: list[dict[str, Any]],
    *,
    require_current: bool = False,
) -> ExecutionPlan:
    decision = orchestrate_request(messages, require_current=require_current)
    objective = _latest_user_text(messages)[:2000]
    steps: list[ExecutionStep] = [
        ExecutionStep(
            "s1",
            "planner",
            "understand request, constraints and context",
            None,
            (),
            True,
            False,
        )
    ]

    action = decision.primary_action
    if action == "research":
        steps.extend(
            [
                ExecutionStep("s2", "researcher", "gather independent current evidence", "web.search", ("s1",), True, True),
                ExecutionStep("s3", "researcher", "synthesize and resolve source conflicts", "research.run", ("s2",), True, True),
            ]
        )
        last = "s3"
    elif action == "code_agent":
        steps.extend(
            [
                ExecutionStep("s2", "coder", "map affected code and dependencies", "code.graph", ("s1",), True, False),
                ExecutionStep("s3", "coder", "produce targeted repair", "code.repair", ("s2",), True, True),
                ExecutionStep("s4", "tester", "run focused regression checks", "tests.run", ("s3",), True, True),
            ]
        )
        last = "s4"
    elif action == "image":
        steps.append(ExecutionStep("s2", "creator", "generate with identity and attribute locks", "image.generate", ("s1",), True, True))
        last = "s2"
    elif action == "artifact":
        steps.append(ExecutionStep("s2", "creator", "create requested artifact using the correct workflow", "artifact.create", ("s1",), True, True))
        last = "s2"
    elif action == "calculator":
        steps.append(ExecutionStep("s2", "calculator", "compute deterministic result", "calculator.run", ("s1",), True, True))
        last = "s2"
    else:
        steps.append(ExecutionStep("s2", "solver", "produce direct answer", None, ("s1",), True, decision.verify_after))
        last = "s2"

    if decision.verify_after and action not in {"research", "code_agent"}:
        steps.append(ExecutionStep("s3", "critic", "verify completeness, correctness and contradictions", None, (last,), True, True))
        last = "s3"

    steps.append(
        ExecutionStep(
            f"s{len(steps)+1}",
            "reviewer",
            "deliver concise result and next action",
            None,
            (last,),
            True,
            False,
        )
    )

    return ExecutionPlan(
        objective=objective,
        mode=action,
        steps=tuple(steps),
        confirmation_required=decision.confirmation_required,
        parallelizable=decision.parallelizable,
        max_repair_attempts=decision.retry_budget,
        orchestration=decision,
    )
