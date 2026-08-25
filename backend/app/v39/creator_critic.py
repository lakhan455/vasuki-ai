from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CreatorReview:
    version: str
    score: int
    checks: tuple[str, ...]
    warnings: tuple[str, ...]
    ready: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["checks"] = list(self.checks)
        data["warnings"] = list(self.warnings)
        return data


def review_code_plan(telemetry: dict[str, Any]) -> CreatorReview:
    checks = (
        "objective compiled",
        "bounded patch policy present",
        "verification plan present",
        "evidence-only completion policy present",
    )
    warnings: list[str] = []
    spec = telemetry.get("spec") or {}
    patch = telemetry.get("patch") or {}
    verify = telemetry.get("verification") or {}

    if not str(spec.get("objective") or "").strip():
        warnings.append("coding objective is empty")
    if int(patch.get("max_changed_files") or 0) <= 0:
        warnings.append("patch scope is not bounded")
    if not (verify.get("static_checks") or verify.get("targeted_checks")):
        warnings.append("no validation candidates were identified")

    score = max(0, 100 - len(warnings) * 25)
    return CreatorReview("v39", score, checks, tuple(warnings), not warnings)


def review_image_plan(plan: dict[str, Any]) -> CreatorReview:
    checks = (
        "subject intent preserved",
        "composition direction present",
        "fidelity policy present",
        "provider policy explicit",
    )
    warnings: list[str] = []
    if not plan.get("image_type"):
        warnings.append("image type is unresolved")
    if not plan.get("quality_mode"):
        warnings.append("quality mode is missing")
    if not plan.get("routing_policy"):
        warnings.append("routing policy is missing")

    score = max(0, 100 - len(warnings) * 25)
    return CreatorReview("v39", score, checks, tuple(warnings), not warnings)


def creator_critic_health() -> dict[str, Any]:
    return {
        "version": "v39",
        "name": "Creator Quality Critic",
        "features": [
            "coding-plan-preflight",
            "image-plan-preflight",
            "deterministic-quality-checks",
            "no-extra-model-call",
            "no-fake-success-claim",
        ],
        "extra_provider_call_required": False,
        "hidden_chain_of_thought_exposed": False,
    }
