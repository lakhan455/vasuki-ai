from __future__ import annotations

from typing import Any


def health_snapshot() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v56",
        "name": "Vasuki Focused Workspace UI",
        "features": [
            "task-aware-live-status",
            "answer-confidence-chip",
            "quality-checked-chip",
            "verified-source-chip",
            "source-disagreement-warning",
            "technical-diagnostics-deemphasized",
        ],
        "frontend_only_visual_breaking_change": False,
        "new_dependency_required": False,
    }
