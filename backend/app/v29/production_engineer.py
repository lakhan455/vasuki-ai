from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ReleaseGuard:
    version: str
    production_related: bool
    required_checks: tuple[str, ...]
    migration_policy: str
    rollback_policy: str
    confirmation_required_for_deploy: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["required_checks"] = list(self.required_checks)
        return data


def build_release_guard(text: str) -> ReleaseGuard:
    low = str(text or "").casefold()
    prod = any(x in low for x in ("production", "deploy", "render", "vercel", "release", "main branch"))
    checks = (
        "working tree/change set understood",
        "targeted tests pass",
        "full regression suite appropriate to change passes",
        "frontend build/type checks pass when frontend changed",
        "diff/checks contain no unintended files",
        "health endpoint verified after deploy",
    ) if prod else ("normal task validation",)
    return ReleaseGuard(
        version="v29",
        production_related=prod,
        required_checks=checks,
        migration_policy="never apply database migration blindly; inspect and require explicit rollout decision",
        rollback_policy="preserve previous known-good release and define rollback trigger",
        confirmation_required_for_deploy=prod,
    )


def production_engineer_health() -> dict[str, Any]:
    return {
        "version": "v29",
        "name": "Production Engineer Brain",
        "features": [
            "release-gate-checklist",
            "migration-safety-policy",
            "rollback-plan-policy",
            "post-deploy-health-verification",
            "explicit-deploy-confirmation",
        ],
        "blind_db_migration": False,
        "automatic_deploy_without_confirmation": False,
    }
