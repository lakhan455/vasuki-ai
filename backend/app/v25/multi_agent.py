from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentRole:
    role: str
    responsibility: str


@dataclass(frozen=True, slots=True)
class AgentTeam:
    version: str
    roles: tuple[AgentRole, ...]
    coordination: str
    extra_provider_calls_required: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["roles"] = [asdict(role) for role in self.roles]
        return data


def build_agent_team(*, coding: bool, security_sensitive: bool, complex_task: bool) -> AgentTeam:
    roles = [AgentRole("planner", "Own objective, constraints, and execution order.")]
    if coding:
        roles.extend([
            AgentRole("repo-reader", "Inspect relevant files, symbols, imports, routes, and callers."),
            AgentRole("implementer", "Design the smallest compatible change."),
            AgentRole("reviewer", "Challenge regressions, interfaces, and unsupported assumptions."),
            AgentRole("tester", "Define evidence needed to validate the change."),
        ])
    if security_sensitive:
        roles.append(AgentRole("security-reviewer", "Check auth, permission, secret, and trust boundaries."))
    if complex_task and not coding:
        roles.append(AgentRole("critic", "Check completeness and contradictions."))

    return AgentTeam(
        version="v25",
        roles=tuple(roles),
        coordination="single-runtime-role-sequencing-with-shared-evidence",
        extra_provider_calls_required=False,
    )


def multi_agent_health() -> dict[str, Any]:
    return {
        "version": "v25",
        "name": "Multi-Agent Coordination Brain",
        "features": [
            "planner-role",
            "repo-reader-role",
            "implementer-role",
            "reviewer-role",
            "tester-role",
            "conditional-security-reviewer",
            "shared-evidence-contract",
        ],
        "extra_provider_calls_required": False,
        "hidden_chain_of_thought_exposed": False,
    }
