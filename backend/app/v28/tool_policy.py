from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.v13.intelligence import analyze_intent


@dataclass(frozen=True, slots=True)
class ToolDecision:
    version: str
    tools: tuple[str, ...]
    reasons: tuple[str, ...]
    external_side_effect_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tools"] = list(self.tools)
        data["reasons"] = list(self.reasons)
        return data


def choose_tools(messages: list[dict[str, Any]], *, project_active: bool, allow_web: bool) -> ToolDecision:
    intent = analyze_intent(messages, require_current=False)
    tools: list[str] = []
    reasons: list[str] = []
    if intent.needs_calculator:
        tools.append("calculator")
        reasons.append("deterministic calculation requested")
    if allow_web:
        tools.append("verified-web")
        reasons.append("fresh or explicitly requested evidence")
    if project_active and intent.task_type == "code":
        tools.append("project-kb")
        reasons.append("active project coding evidence")
    if intent.needs_files:
        tools.append("artifact-builder")
        reasons.append("downloadable artifact requested")
    if intent.needs_image:
        tools.append("image-studio")
        reasons.append("visual generation requested")
    if intent.needs_code_agent:
        tools.append("coding-agent")
        reasons.append("complex coding task detected")
    if not tools:
        tools.append("none")
        reasons.append("direct answer is sufficient")
    return ToolDecision(
        version="v28",
        tools=tuple(tools),
        reasons=tuple(reasons),
        external_side_effect_allowed=False,
    )


def tool_policy_health() -> dict[str, Any]:
    return {
        "version": "v28",
        "name": "Tool Selection Brain",
        "features": [
            "minimal-tool-selection",
            "web-only-when-justified",
            "project-kb-for-active-code",
            "deterministic-calculator-preference",
            "no-unconfirmed-side-effects",
        ],
        "automatic_external_side_effect": False,
    }
