from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.v31.coding_spec import CodingSpec
from app.v32.impact_engine import ImpactPlan


@dataclass(frozen=True, slots=True)
class PatchStrategy:
    version: str
    mode: str
    max_changed_files: int
    preserve_public_contracts: bool
    require_targeted_test: bool
    require_security_review: bool
    edit_order: tuple[str, ...]
    completion_policy: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["edit_order"] = list(self.edit_order)
        return data


def build_patch_strategy(spec: CodingSpec, impact: ImpactPlan) -> PatchStrategy:
    scope = len(impact.primary_files) + len(impact.related_files)
    max_files = min(16, max(3, scope + (2 if spec.operation == "implement" else 1)))
    return PatchStrategy(
        version="v33",
        mode=(
            "bounded-feature-implementation"
            if spec.operation == "implement"
            else "minimal-compatible-patch"
        ),
        max_changed_files=max_files,
        preserve_public_contracts=spec.operation in {
            "debug-repair", "refactor", "inspect-modify", "test-regression"
        },
        require_targeted_test=(
            spec.operation in {"debug-repair", "test-regression"}
            or spec.regression_risk in {"medium", "high"}
        ),
        require_security_review=spec.security_sensitive,
        edit_order=impact.dependency_order[:max_files],
        completion_policy=(
            "never claim execution, tests, deployment, or migration success without direct evidence"
        ),
    )


def patch_brain_health() -> dict[str, Any]:
    return {
        "version": "v33",
        "name": "Minimal Patch Brain",
        "features": [
            "bounded-change-scope",
            "interface-preservation",
            "dependency-aware-edit-order",
            "targeted-regression-policy",
            "security-review-gate",
            "evidence-only-completion-claims",
        ],
        "automatic_destructive_change": False,
    }
