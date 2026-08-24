from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class QualityGate:
    version: str
    checks: tuple[str, ...]
    repair_if: tuple[str, ...]
    unsupported_claim_policy: str
    completion_threshold: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["checks"] = list(self.checks)
        data["repair_if"] = list(self.repair_if)
        return data


def build_quality_gate(*, current_required: bool, coding: bool, destructive: bool) -> QualityGate:
    checks = ["answer addresses latest user intent", "no contradiction with supplied context"]
    if current_required:
        checks.append("current claims grounded in fresh evidence")
    if coding:
        checks.extend(["interfaces preserved or change explicitly justified", "validation claims have evidence"])
    if destructive:
        checks.append("explicit approval exists before destructive action")
    return QualityGate(
        version="v26",
        checks=tuple(checks),
        repair_if=("missing requested result", "unsupported factual claim", "contradictory change plan", "fake validation claim"),
        unsupported_claim_policy="downgrade certainty or request/inspect evidence",
        completion_threshold="all required gates satisfied",
    )


def self_correction_health() -> dict[str, Any]:
    return {
        "version": "v26",
        "name": "Self-Correction and Quality Gate",
        "features": [
            "intent-completeness-check",
            "evidence-grounding-check",
            "coding-interface-check",
            "validation-claim-check",
            "destructive-confirmation-check",
        ],
        "hidden_chain_of_thought_exposed": False,
        "extra_provider_call_required": False,
    }
