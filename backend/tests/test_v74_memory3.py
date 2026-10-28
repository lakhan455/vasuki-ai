from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.v74.memory3 import (
    MemoryItem,
    build_memory_context,
    health_snapshot,
    resolve_memory,
    session_items,
)


NOW = datetime(2026, 10, 28, tzinfo=timezone.utc)


def item(scope: str, text: str, key: str, days: int = 0, kind: str = "preference"):
    return MemoryItem(
        scope=scope,
        key=key,
        text=text,
        kind=kind,
        updated_at=NOW - timedelta(days=days),
        source="test",
    )


def test_v74_scope_priority_session_over_project_over_personal():
    resolved = resolve_memory(
        [
            item("personal", "Preferred price: 199", "price", 1),
            item("project", "Preferred price: 299", "price", 2),
            item("session", "For now preferred price: 399", "price", 0, "temporary"),
        ],
        query="preferred price",
        now=NOW,
    )
    selected = resolved["selected"]
    assert any(row.scope == "session" and "399" in row.text for row in selected)
    assert not any("299" in row.text for row in selected)
    assert not any("199" in row.text for row in selected)
    assert len(resolved["suppressed_conflicts"]) == 2


def test_v74_stale_temporary_memory_is_suppressed_without_deletion():
    resolved = resolve_memory(
        [
            item("personal", "For now use short answers", "answer-style", 20, "temporary"),
            item("personal", "Use friendly answers", "tone", 100, "preference"),
        ],
        query="answer style",
        now=NOW,
    )
    assert len(resolved["stale"]) == 1
    assert resolved["stale"][0].kind == "temporary"
    assert any("friendly" in row.text.casefold() for row in resolved["selected"])


def test_v74_session_memory_extracts_temporary_current_conversation():
    rows = session_items(
        [
            {"role": "user", "content": "For now call me Captain."},
            {"role": "assistant", "content": "Okay."},
            {"role": "user", "content": "Explain the plan."},
        ]
    )
    assert rows
    assert rows[0].scope == "session"
    assert "Captain" in rows[0].text


def test_v74_context_has_explicit_conflict_policy():
    resolved = resolve_memory(
        [item("project", "Project decision: keep API compatible", "api-compat")],
        query="API",
        now=NOW,
    )
    context = build_memory_context(resolved)
    assert "current conversation > active project > personal memory" in context
    assert "Project decision" in context


def test_v74_health_is_truthful():
    health = health_snapshot()
    assert health["version"] == "v74"
    assert health["silent_persistent_writes"] is False
    assert health["destructive_stale_cleanup"] is False
    assert health["new_database_migration_required"] is False


def test_v74_production_wiring_present():
    repo = Path(__file__).resolve().parents[2]
    main = (repo / "backend/app/main_v11.py").read_text(encoding="utf-8")
    assert '"/health/v74"' in main
    assert '"/api/v74/memory/inspect"' in main
    assert "_v74_private_context" in main
    assert "v10.legacy._private_context = _v74_private_context" in main
