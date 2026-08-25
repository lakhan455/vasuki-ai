from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any

_PATH = re.compile(r"(?<![\w.-])((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+)")
_STACKS = (
    "python", "fastapi", "django", "flask", "javascript", "typescript",
    "react", "next.js", "nextjs", "node", "express", "vite", "html",
    "css", "tailwind", "kotlin", "android", "gradle", "flutter", "dart",
    "java", "spring", "rust", "go", "supabase", "postgres", "mysql",
    "sqlite", "docker", "vercel", "render",
)
_SECURITY = (
    "auth", "login", "password", "token", "secret", "permission",
    "role", "admin", "payment", "webhook",
)


@dataclass(frozen=True, slots=True)
class CodingSpec:
    version: str
    objective: str
    operation: str
    stacks: tuple[str, ...]
    target_paths: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    constraints: tuple[str, ...]
    security_sensitive: bool
    regression_risk: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("stacks", "target_paths", "acceptance_criteria", "constraints"):
            data[key] = list(data[key])
        return data


def _operation(text: str) -> str:
    low = text.casefold()
    if any(x in low for x in ("traceback", "exception", "error", "bug", "fix", "repair", "debug")):
        return "debug-repair"
    if any(x in low for x in ("refactor", "cleanup", "restructure")):
        return "refactor"
    if any(x in low for x in ("test", "pytest", "regression")):
        return "test-regression"
    if any(x in low for x in ("add", "implement", "create", "build", "feature")):
        return "implement"
    return "inspect-modify"


def compile_coding_spec(
    prompt: str,
    *,
    existing_files: list[dict[str, str]] | None = None,
) -> CodingSpec:
    text = " ".join(str(prompt or "").split()).strip()
    low = text.casefold()
    stacks = tuple(stack for stack in _STACKS if stack in low)

    paths: list[str] = []
    for match in _PATH.finditer(text):
        value = match.group(1).replace("\\", "/")
        if value not in paths:
            paths.append(value)

    existing_paths = [
        str(item.get("path") or "").replace("\\", "/")
        for item in (existing_files or [])
        if str(item.get("path") or "").strip()
    ]
    for mentioned in list(paths):
        name = PurePosixPath(mentioned).name.casefold()
        for path in existing_paths:
            if PurePosixPath(path).name.casefold() == name and path not in paths:
                paths.append(path)

    criteria = [
        "requested behavior works without removing unrelated existing behavior",
        "changed interfaces remain compatible unless a breaking change was explicitly requested",
        "errors are handled with useful user/developer diagnostics",
    ]
    if any(x in low for x in ("frontend", "react", "next", "ui", "page", "component")):
        criteria.append("frontend build and type checks remain clean for changed UI code")
    if any(x in low for x in ("api", "fastapi", "endpoint", "backend", "route")):
        criteria.append("API request and response contracts stay compatible unless explicitly changed")
    if any(x in low for x in ("test", "bug", "fix", "repair", "regression")):
        criteria.append("a targeted regression check covers the reported failure")

    constraints: list[str] = []
    for token, label in (
        ("no migration", "do not add or apply a database migration"),
        ("no new api key", "do not require a new API key"),
        ("without changing", "preserve explicitly protected behavior"),
        ("only", "keep change scope targeted to the requested area"),
    ):
        if token in low:
            constraints.append(label)

    security = any(token in low for token in _SECURITY)
    operation = _operation(text)
    risk = (
        "high"
        if security or any(x in low for x in ("production", "migration", "payment", "auth"))
        else "medium"
        if operation != "inspect-modify"
        else "low"
    )

    return CodingSpec(
        version="v31",
        objective=text[:1800],
        operation=operation,
        stacks=stacks[:12],
        target_paths=tuple(paths[:12]),
        acceptance_criteria=tuple(criteria[:8]),
        constraints=tuple(constraints[:8]),
        security_sensitive=security,
        regression_risk=risk,
    )


def coding_spec_health() -> dict[str, Any]:
    return {
        "version": "v31",
        "name": "Coding Specification Compiler",
        "features": [
            "objective-normalization",
            "operation-classification",
            "stack-detection",
            "target-file-hints",
            "acceptance-criteria-generation",
            "security-and-regression-risk-signals",
        ],
        "extra_provider_call_required": False,
        "db_migration_required": False,
    }
