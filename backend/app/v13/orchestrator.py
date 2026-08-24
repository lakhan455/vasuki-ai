from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from app.v13.intelligence import IntelligencePlan, analyze_intent


_WRITE_RISK = re.compile(
    r"\b(?:delete\s+(?:repo|repository|database|table|file)|drop\s+table|"
    r"deploy\s+(?:to\s+)?production|push\s+(?:to\s+)?main|merge\s+(?:the\s+)?(?:pr|pull request)|"
    r"send\s+(?:the\s+)?(?:email|message)|make\s+(?:a\s+)?payment|purchase|buy\s+now)\b",
    re.I,
)


@dataclass(frozen=True, slots=True)
class OrchestrationDecision:
    primary_action: str
    tools: tuple[str, ...]
    verify_after: bool
    confirmation_required: bool
    retry_budget: int
    parallelizable: bool
    intelligence: IntelligencePlan
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tools"] = list(self.tools)
        data["reasons"] = list(self.reasons)
        data["intelligence"] = self.intelligence.to_dict()
        return data


def orchestrate_request(
    messages: list[dict[str, Any]],
    *,
    require_current: bool = False,
) -> OrchestrationDecision:
    plan = analyze_intent(messages, require_current=require_current)
    latest = next(
        (
            str(item.get("content") or "")
            for item in reversed(messages)
            if item.get("role") == "user"
        ),
        "",
    )

    if plan.needs_image:
        action = "image"
        tools = ("image.generate",)
    elif plan.needs_files:
        action = "artifact"
        tools = ("artifact.create",)
    elif plan.needs_calculator and plan.task_type != "code":
        action = "calculator"
        tools = ("calculator.run",)
    elif plan.needs_code_agent:
        action = "code_agent"
        tools = ("code.graph", "code.repair", "tests.run")
    elif plan.needs_web:
        action = "research"
        tools = ("web.search", "research.run")
    else:
        action = "chat"
        tools = ()

    confirmation_required = bool(_WRITE_RISK.search(latest))
    retry_budget = 3 if plan.difficulty == "high" else 2 if plan.difficulty == "medium" else 1
    parallelizable = action == "research" or (
        action == "code_agent" and plan.difficulty == "high"
    )

    reasons = list(plan.reasons)
    reasons.append(f"primary action selected: {action}")
    if confirmation_required:
        reasons.append("write/destructive action requires explicit confirmation")

    return OrchestrationDecision(
        primary_action=action,
        tools=tools,
        verify_after=bool(plan.needs_verification or action in {"research", "code_agent", "calculator"}),
        confirmation_required=confirmation_required,
        retry_budget=retry_budget,
        parallelizable=parallelizable,
        intelligence=plan,
        reasons=tuple(reasons),
    )
