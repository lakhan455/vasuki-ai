from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any

from app.v31.coding_spec import CodingSpec


@dataclass(frozen=True, slots=True)
class VerificationPlan:
    version: str
    static_checks: tuple[str, ...]
    targeted_checks: tuple[str, ...]
    release_checks: tuple[str, ...]
    commands_are_candidates_only: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("static_checks", "targeted_checks", "release_checks"):
            data[key] = list(data[key])
        return data


def build_verification_plan(
    spec: CodingSpec,
    existing_files: list[dict[str, str]] | None = None,
) -> VerificationPlan:
    paths = [str(item.get("path") or "") for item in (existing_files or [])]
    names = {PurePosixPath(path).name.casefold() for path in paths}
    suffixes = {PurePosixPath(path).suffix.casefold() for path in paths}

    static: list[str] = ["git diff --check"]
    targeted: list[str] = []

    if ".py" in suffixes:
        static.append("python -m compileall <changed-python-paths>")
        if any("test" in path.casefold() for path in paths):
            targeted.append("python -m pytest <targeted-tests> -q")

    if "package.json" in names or any(s in suffixes for s in (".ts", ".tsx", ".js", ".jsx")):
        static.extend(["npm run build", "npm run lint"])

    if any(s in suffixes for s in (".kt", ".java")) or {"build.gradle", "build.gradle.kts"} & names:
        targeted.append("run the repository existing Gradle test/build task")

    if ".rs" in suffixes:
        targeted.append("cargo check")
    if ".go" in suffixes:
        targeted.append("go test ./...")

    release = [
        "review changed file list for unintended files",
        "verify health endpoint after deployment when production is changed",
        "define rollback path before irreversible production change",
    ]
    if "do not add or apply a database migration" in spec.constraints:
        release.append("confirm no migration file or schema rollout was introduced")

    return VerificationPlan(
        version="v34",
        static_checks=tuple(dict.fromkeys(static)),
        targeted_checks=tuple(dict.fromkeys(targeted)),
        release_checks=tuple(release),
        commands_are_candidates_only=True,
    )


def verification_engine_health() -> dict[str, Any]:
    return {
        "version": "v34",
        "name": "Evidence Verification Engine",
        "features": [
            "language-aware-validation-plan",
            "targeted-regression-plan",
            "diff-scope-check",
            "release-health-check-policy",
            "rollback-evidence-policy",
        ],
        "commands_execute_automatically": False,
        "blind_db_migration": False,
    }
