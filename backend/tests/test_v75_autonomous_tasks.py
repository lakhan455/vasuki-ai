from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.v75 import autonomous_tasks as tasks


class Settings:
    supabase_url = "https://example.supabase.co"
    supabase_service_role_key = "secret"


def test_v75_prompt_round_trip_and_legacy_compatibility():
    encoded = tasks._encode_prompt("Check the latest numbers.", "research")
    assert tasks.decode_prompt(encoded) == {
        "mode": "research",
        "prompt": "Check the latest numbers.",
    }
    assert tasks.decode_prompt("legacy task") == {
        "mode": "chat",
        "prompt": "legacy task",
    }


def test_v75_health_is_truthful():
    health = tasks.health_snapshot(Settings())
    assert health["version"] == "v75"
    assert health["persistent_scheduler_available"] is True
    assert health["event_triggers"]["available"] is False
    assert health["runtime"]["exact_wake_on_sleeping_free_host"] is False
    assert health["new_database_migration_required"] is False


def test_v75_create_reuses_existing_scheduler(monkeypatch):
    captured = {}

    async def fake_create(settings, **kwargs):
        captured.update(kwargs)
        return {
            "id": "task-1",
            "title": kwargs["title"],
            "prompt": kwargs["prompt"],
            "run_at": kwargs["run_at"],
            "cron": kwargs["cron"],
            "status": "scheduled",
            "last_run_at": None,
            "result": None,
            "created_at": "2026-10-28T00:00:00+00:00",
        }

    monkeypatch.setattr(tasks, "create_v11_task", fake_create)
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    result = asyncio.run(
        tasks.create_task(
            Settings(),
            user_id="user-1",
            title="Daily market check",
            prompt="Summarize the market.",
            mode="chat",
            run_at=future,
        )
    )
    assert result["id"] == "task-1"
    assert result["mode"] == "chat"
    assert result["prompt"] == "Summarize the market."
    assert captured["prompt"].startswith("[V75]")


def test_v75_chat_executor(monkeypatch):
    async def fake_chat(*args, **kwargs):
        return "Completed scheduled analysis.", "fake-provider"

    monkeypatch.setattr(tasks, "route_chat_v10", fake_chat)
    result = asyncio.run(
        tasks.execute_scheduled_task(
            Settings(),
            {
                "user_id": "user-1",
                "prompt": tasks._encode_prompt("Analyze this.", "chat"),
            },
        )
    )
    assert result["mode"] == "chat"
    assert result["answer"] == "Completed scheduled analysis."


def test_v75_research_executor(monkeypatch):
    async def fake_research(prompt, settings):
        return {
            "answer": "Research complete.",
            "provider": "fake-research",
            "sources": [{"title": "A", "url": "https://example.com"}],
        }

    monkeypatch.setattr(tasks, "run_research", fake_research)
    result = asyncio.run(
        tasks.execute_scheduled_task(
            Settings(),
            {
                "user_id": "user-1",
                "prompt": tasks._encode_prompt("Research this.", "research"),
            },
        )
    )
    assert result["mode"] == "research"
    assert len(result["sources"]) == 1


def test_v75_pause_resume_cancel(monkeypatch):
    row = {
        "id": "task-1",
        "user_id": "user-1",
        "title": "Task",
        "prompt": tasks._encode_prompt("Do it.", "chat"),
        "run_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "cron": None,
        "status": "scheduled",
    }

    async def fake_get(settings, *, user_id, task_id):
        return dict(row)

    async def fake_patch(settings, *, user_id, task_id, payload):
        return tasks.public_task({**row, **payload})

    monkeypatch.setattr(tasks, "_get_raw_task", fake_get)
    monkeypatch.setattr(tasks, "_patch_task", fake_patch)

    paused = asyncio.run(
        tasks.pause_task(Settings(), user_id="user-1", task_id="task-1")
    )
    assert paused["status"] == "paused"

    row["status"] = "paused"
    resumed = asyncio.run(
        tasks.resume_task(Settings(), user_id="user-1", task_id="task-1")
    )
    assert resumed["status"] == "scheduled"

    row["status"] = "scheduled"
    cancelled = asyncio.run(
        tasks.cancel_task(Settings(), user_id="user-1", task_id="task-1")
    )
    assert cancelled["status"] == "cancelled"


def test_v75_production_wiring_present():
    repo = Path(__file__).resolve().parents[2]
    main = (repo / "backend/app/main_v11.py").read_text(encoding="utf-8")
    api = (repo / "frontend/lib/api.ts").read_text(encoding="utf-8")
    operations = (repo / "frontend/app/operations/page.tsx").read_text(encoding="utf-8")

    assert '"/health/v75"' in main
    assert '"/api/v75/tasks"' in main
    assert "v75_execute_scheduled_task" in main
    assert "createAutonomousTaskV75" in api
    assert "fetchAutonomousTasksV75" in operations
    assert "Autonomous tasks" in operations
