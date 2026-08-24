from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.v19.project_coding_brain import decide_project_coding


@dataclass(frozen=True, slots=True)
class CodingStrategy:
    version: str
    action: str
    inspect_first: bool
    preserve_interfaces: bool
    require_regression_plan: bool
    security_review: bool
    preferred_change_scope: str
    completion_claim_policy: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_coding_strategy(messages: list[dict[str, Any]], *, project_id: str = "") -> CodingStrategy:
    decision = decide_project_coding(messages, project_id=project_id)
    return CodingStrategy(
        version="v21",
        action=decision.action,
        inspect_first=bool(decision.needs_project_files),
        preserve_interfaces=decision.action in {"debug-repair", "refactor", "inspect-modify"},
        require_regression_plan=decision.needs_test_plan,
        security_review=decision.needs_security_check,
        preferred_change_scope="minimal-targeted-compatible",
        completion_claim_policy="claim execution/tests only when actual evidence exists",
    )


def coding_brain_health() -> dict[str, Any]:
    return {
        "version": "v21",
        "name": "Strong Coding Brain",
        "features": [
            "inspect-before-edit",
            "minimal-compatible-change",
            "public-interface-preservation",
            "regression-plan-required",
            "security-aware-code-policy",
            "no-fake-test-claims",
        ],
        "db_migration_required": False,
        "new_api_key_required": False,
    }
