from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    version: str
    priority: tuple[str, ...]
    write_policy: str
    conflict_policy: str
    sensitive_data_policy: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["priority"] = list(self.priority)
        return data


def build_memory_policy(*, project_active: bool, explicit_memory_command: bool = False) -> MemoryPolicy:
    priority = ["current-conversation"]
    if project_active:
        priority.append("active-project")
    priority.extend(["private-user-memory", "user-documents", "verified-external-evidence"])
    return MemoryPolicy(
        version="v27",
        priority=tuple(priority),
        write_policy="explicit-user-request-only" if explicit_memory_command else "no-new-persistent-write",
        conflict_policy="new-explicit-user-statement-overrides-older-context; otherwise surface uncertainty",
        sensitive_data_policy="never persist passwords, OTPs, API keys, or secrets",
    )


def memory_layers_health() -> dict[str, Any]:
    return {
        "version": "v27",
        "name": "Hierarchical Memory Controller",
        "features": [
            "conversation-first-memory",
            "active-project-priority",
            "private-memory-before-web",
            "explicit-write-policy",
            "memory-conflict-policy",
            "sensitive-data-no-store-policy",
        ],
        "silent_memory_write": False,
        "db_migration_required": False,
    }
