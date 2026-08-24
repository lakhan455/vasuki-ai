from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DeploymentCheck:
    ready: bool
    score: int
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["blockers"] = list(self.blockers)
        data["warnings"] = list(self.warnings)
        return data


def check_deployment(
    changed_paths: list[str],
    *,
    tests_passed: bool,
    backup_ready: bool,
    pending_migrations: list[str] | None = None,
    secrets_exposed: bool = False,
) -> DeploymentCheck:
    paths = [str(path).replace("\\", "/") for path in changed_paths]
    migrations = pending_migrations or []
    blockers: list[str] = []
    warnings: list[str] = []
    score = 100

    if not tests_passed:
        blockers.append("tests are not confirmed passing")
        score -= 35
    if secrets_exposed:
        blockers.append("secret exposure/rotation is unresolved")
        score -= 45
    if migrations and not backup_ready:
        blockers.append("database migrations are pending without a confirmed backup/rollback point")
        score -= 35
    if any(path.endswith(".env") or "/.env" in path for path in paths):
        blockers.append("environment secret file appears in the change set")
        score -= 50
    if any("supabase/" in path and path.endswith(".sql") for path in paths) and not migrations:
        warnings.append("SQL change detected; explicitly record migration order before production rollout")
        score -= 8
    if any(path.startswith("frontend/") for path in paths) and any(path.startswith("backend/") for path in paths):
        warnings.append("cross-stack change detected; run frontend build plus backend tests")
        score -= 4

    return DeploymentCheck(not blockers, max(0, score), tuple(blockers), tuple(warnings))
