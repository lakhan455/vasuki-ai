from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


_DANGEROUS = re.compile(
    r"(?:\brm\s+-rf\b|\bformat\s+[a-z]:|\bdrop\s+database\b|\bdrop\s+table\b|"
    r"\bdel\s+/[fsq]\b|\bremove-item\b.*\b-recurse\b.*\b-force\b|"
    r"\bgit\s+reset\s+--hard\b|\bgit\s+clean\s+-fd\b)",
    re.I,
)


@dataclass(frozen=True, slots=True)
class ValidationPolicy:
    version: str
    safe_commands: tuple[str, ...]
    blocked_patterns: tuple[str, ...]
    network_default: str
    filesystem_default: str
    arbitrary_execution_enabled: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["safe_commands"] = list(self.safe_commands)
        data["blocked_patterns"] = list(self.blocked_patterns)
        return data


def is_command_safe(command: str) -> bool:
    return not bool(_DANGEROUS.search(str(command or "")))


def build_validation_policy(task_type: str = "code") -> ValidationPolicy:
    commands = (
        "python -m pytest -q",
        "python -m compileall <changed-python-paths>",
        "npm run build",
        "npm run lint",
        "git diff --check",
    ) if task_type == "code" else ("read-only inspection",)
    return ValidationPolicy(
        version="v24",
        safe_commands=commands,
        blocked_patterns=("destructive filesystem wipe", "blind database drop", "hard reset/clean without explicit approval"),
        network_default="off-unless-required",
        filesystem_default="project-scoped",
        arbitrary_execution_enabled=False,
    )


def sandbox_health() -> dict[str, Any]:
    return {
        "version": "v24",
        "name": "Safe Validation Sandbox Policy",
        "features": [
            "bounded-validation-command-plan",
            "destructive-command-blocklist",
            "project-scoped-filesystem-policy",
            "network-off-by-default-policy",
        ],
        "arbitrary_server_code_execution": False,
        "db_migration_required": False,
    }
