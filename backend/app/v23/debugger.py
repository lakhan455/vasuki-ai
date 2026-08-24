from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


_ERROR = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))\b")
_HTTP = re.compile(r"\b(?:HTTP\s*)?([45]\d\d)\b", re.I)


@dataclass(frozen=True, slots=True)
class DebugPlan:
    version: str
    layer: str
    signatures: tuple[str, ...]
    checks: tuple[str, ...]
    repair_order: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("signatures", "checks", "repair_order"):
            data[key] = list(data[key])
        return data


def build_debug_plan(text: str) -> DebugPlan:
    low = str(text or "").casefold()
    signatures = []
    for value in [m.group(1) for m in _ERROR.finditer(text)] + [m.group(1) for m in _HTTP.finditer(text)]:
        if value not in signatures:
            signatures.append(value)

    if any(x in low for x in ("render", "vercel", "deploy", "build failed", "docker")):
        layer = "deployment"
        checks = ("entrypoint/config", "environment availability", "build/runtime logs", "health endpoint")
    elif any(x in low for x in ("react", "next", "browser", "hydration", "typescript", "tsx")):
        layer = "frontend"
        checks = ("reproduction path", "component/state flow", "network response", "build/type check")
    elif any(x in low for x in ("sql", "supabase", "database", "constraint", "migration")):
        layer = "data"
        checks = ("query/schema contract", "migration state", "authorization policy", "rollback compatibility")
    else:
        layer = "backend"
        checks = ("stack trace origin", "input contract", "callers/dependencies", "targeted regression test")

    return DebugPlan(
        version="v23",
        layer=layer,
        signatures=tuple(signatures[:10]),
        checks=checks,
        repair_order=("reproduce/identify", "inspect evidence", "minimal repair", "regression validation", "explain residual risk"),
    )


def debugger_health() -> dict[str, Any]:
    return {
        "version": "v23",
        "name": "Autonomous Debugger",
        "features": [
            "error-signature-parsing",
            "failure-layer-classification",
            "evidence-first-debugging",
            "minimal-repair-order",
            "regression-validation-policy",
        ],
        "automatic_destructive_fix": False,
        "db_migration_required": False,
    }
