from pathlib import Path

from app.v71.project_brain import encode_entry, health_snapshot, parse_entry


def test_v71_structured_entry_roundtrip():
    text = encode_entry(
        "task",
        {
            "title": "Ship V71",
            "status": "in_progress",
            "priority": "high",
            "notes": "Keep old data safe",
        },
    )
    item = parse_entry(
        {"id": "abc", "memory_text": text, "source": "v71"}
    )
    assert item is not None
    assert item["id"] == "abc"
    assert item["kind"] == "task"
    assert item["status"] == "in_progress"
    assert item["priority"] == "high"


def test_v71_requires_no_database_migration():
    health = health_snapshot()
    assert health["ok"] is True
    assert health["version"] == "v71"
    assert health["storage"]["new_database_migration_required"] is False
    assert health["old_project_data_preserved"] is True


def test_v71_backend_wiring_present():
    repo = Path(__file__).resolve().parents[2]
    main_v11 = (repo / "backend/app/main_v11.py").read_text(encoding="utf-8")
    assert '"/health/v71"' in main_v11
    assert '"/api/v71/projects/{project_id}/brain"' in main_v11
    assert "v71_project_brain_snapshot" in main_v11
    assert "v71_add_task" in main_v11
    assert "v71_update_task" in main_v11


def test_v71_frontend_project_brain_ui_present():
    repo = Path(__file__).resolve().parents[2]
    api = (repo / "frontend/lib/api.ts").read_text(encoding="utf-8")
    page = (repo / "frontend/app/projects/page.tsx").read_text(encoding="utf-8")
    css = (repo / "frontend/app/globals.css").read_text(encoding="utf-8")
    assert "fetchProjectBrainV71" in api
    assert "setProjectGoalV71" in api
    assert "addProjectTaskV71" in api
    assert "updateProjectTaskV71" in api
    assert "Project Brain 3.0" in page
    assert "Last work checkpoint" in page
    assert "pv-v71-brain" in css


def test_v71_project_context_renders_brain_items_readably():
    repo = Path(__file__).resolve().parents[2]
    memory_service = (
        repo / "backend/app/services/project_memory_v8.py"
    ).read_text(encoding="utf-8")
    assert "_render_project_memory_for_context" in memory_service
    assert "PROJECT GOAL" in memory_service
    assert "PROJECT TASK" in memory_service
