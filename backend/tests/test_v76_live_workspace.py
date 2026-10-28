from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.v76 import live_workspace as workspace


class Settings:
    supabase_url = "https://example.supabase.co"
    supabase_service_role_key = "secret"
    supabase_secret_key = None


def test_v76_health_is_truthful_and_no_migration():
    health = workspace.health_snapshot(Settings())
    assert health["version"] == "v76"
    assert health["persistent_storage_available"] is True
    assert health["storage"]["generated-artifact-expiry_applies"] is False
    assert health["safety"]["per_user_ownership"] is True
    assert health["new_database_migration_required"] is False


def test_v76_workspace_create_update_conflict_delete(monkeypatch):
    objects: dict[str, bytes] = {}

    async def fake_list(settings, *, user_id, limit=100):
        prefix = f"{user_id}/v76/meta/"
        return [key for key in objects if key.startswith(prefix)]

    async def fake_upload(settings, *, path, content, content_type, upsert):
        if not upsert and path in objects:
            raise RuntimeError("exists")
        objects[path] = bytes(content)

    async def fake_read(settings, *, path):
        if path not in objects:
            raise FileNotFoundError(path)
        return objects[path]

    async def fake_read_json(settings, *, path):
        return json.loads((await fake_read(settings, path=path)).decode())

    async def fake_delete(settings, *, paths):
        for path in paths:
            objects.pop(path, None)

    monkeypatch.setattr(workspace, "_list_meta_paths", fake_list)
    monkeypatch.setattr(workspace, "_upload_object", fake_upload)
    monkeypatch.setattr(workspace, "_read_object", fake_read)
    monkeypatch.setattr(workspace, "_read_json", fake_read_json)
    monkeypatch.setattr(workspace, "_delete_paths", fake_delete)

    async def scenario():
        created = await workspace.create_workspace(
            Settings(),
            user_id="u1",
            title="Launch plan",
            kind="markdown",
            content="# Hello",
            language="markdown",
        )
        fetched = await workspace.get_workspace(
            Settings(),
            user_id="u1",
            workspace_id=created["id"],
        )
        updated = await workspace.update_workspace(
            Settings(),
            user_id="u1",
            workspace_id=created["id"],
            title="Launch plan v2",
            content="# Updated",
            expected_version=1,
        )
        with pytest.raises(workspace.WorkspaceConflict):
            await workspace.update_workspace(
                Settings(),
                user_id="u1",
                workspace_id=created["id"],
                content="# stale write",
                expected_version=1,
            )
        listed = await workspace.list_workspaces(Settings(), user_id="u1")
        deleted = await workspace.delete_workspace(
            Settings(),
            user_id="u1",
            workspace_id=created["id"],
        )
        return created, fetched, updated, listed, deleted

    created, fetched, updated, listed, deleted = asyncio.run(scenario())
    assert created["version"] == 1
    assert fetched["content"] == "# Hello"
    assert updated["version"] == 2
    assert updated["content"] == "# Updated"
    assert listed[0]["title"] == "Launch plan v2"
    assert deleted is True


def test_v76_rejects_oversized_content():
    with pytest.raises(ValueError):
        workspace._content_bytes("x" * (workspace.MAX_CONTENT_BYTES + 1))


def test_v76_production_wiring_present():
    repo = Path(__file__).resolve().parents[2]
    main = (repo / "backend/app/main_v11.py").read_text(encoding="utf-8")
    api = (repo / "frontend/lib/api.ts").read_text(encoding="utf-8")
    chat = (repo / "frontend/components/ChatApp.tsx").read_text(encoding="utf-8")
    page = (repo / "frontend/app/workspace/page.tsx").read_text(encoding="utf-8")

    assert '"/health/v76"' in main
    assert '"/api/v76/workspaces"' in main
    assert "createWorkspaceV76" in api
    assert 'href="/workspace"' in chat
    assert "Live Workspace" in page
    assert "saveWorkspaceV76" in page
