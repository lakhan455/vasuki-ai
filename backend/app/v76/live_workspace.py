from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from app.v48.file_library import BUCKET, _credentials, _headers, ensure_bucket

MAX_CONTENT_BYTES = 2 * 1024 * 1024
MAX_WORKSPACES = 100
KINDS = {"document", "markdown", "code", "html", "spreadsheet"}

_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class WorkspaceConflict(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_title(value: Any) -> str:
    title = re.sub(r"\s+", " ", str(value or "")).strip()
    if not title:
        title = "Untitled workspace"
    return title[:180]


def _clean_kind(value: Any) -> str:
    kind = str(value or "document").strip().casefold()
    if kind not in KINDS:
        raise ValueError("Unsupported workspace kind.")
    return kind


def _clean_language(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_+.#-]+", "", str(value or "").strip())[:40]


def _content_bytes(content: Any) -> bytes:
    data = str(content or "").encode("utf-8")
    if len(data) > MAX_CONTENT_BYTES:
        raise ValueError("Workspace content exceeds the 2 MB limit.")
    return data


def _assert_id(workspace_id: str) -> str:
    value = str(workspace_id or "").strip().casefold()
    if not _ID_RE.fullmatch(value):
        raise ValueError("Invalid workspace id.")
    return value


def _meta_path(user_id: str, workspace_id: str) -> str:
    return f"{user_id}/v76/meta/{workspace_id}.json"


def _content_path(user_id: str, workspace_id: str) -> str:
    return f"{user_id}/v76/content/{workspace_id}.txt"


async def _upload_object(
    settings: Any,
    *,
    path: str,
    content: bytes,
    content_type: str,
    upsert: bool,
) -> None:
    await ensure_bucket(settings)
    base, key = _credentials(settings)
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{base}/storage/v1/object/{BUCKET}/{path}",
            headers={
                **_headers(key, content_type=content_type),
                "x-upsert": "true" if upsert else "false",
            },
            content=content,
        )
    if response.status_code not in {200, 201}:
        raise RuntimeError(
            f"Workspace storage write failed ({response.status_code}): "
            f"{response.text[:240]}"
        )


async def _read_object(settings: Any, *, path: str) -> bytes:
    await ensure_bucket(settings)
    base, key = _credentials(settings)
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"{base}/storage/v1/object/authenticated/{BUCKET}/{path}",
            headers=_headers(key),
        )
    if response.status_code == 404:
        raise FileNotFoundError(path)
    if response.status_code >= 400:
        raise RuntimeError(
            f"Workspace storage read failed ({response.status_code}): "
            f"{response.text[:240]}"
        )
    return response.content


async def _read_json(settings: Any, *, path: str) -> dict[str, Any]:
    raw = await _read_object(settings, path=path)
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("Workspace metadata is invalid.") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Workspace metadata is invalid.")
    return value


async def _delete_paths(settings: Any, *, paths: list[str]) -> None:
    if not paths:
        return
    await ensure_bucket(settings)
    base, key = _credentials(settings)
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.request(
            "DELETE",
            f"{base}/storage/v1/object/{BUCKET}",
            headers=_headers(key, content_type="application/json"),
            json={"prefixes": paths},
        )
    if response.status_code >= 400 and response.status_code != 404:
        raise RuntimeError(
            f"Workspace deletion failed ({response.status_code}): "
            f"{response.text[:240]}"
        )


async def _list_meta_paths(
    settings: Any,
    *,
    user_id: str,
    limit: int = MAX_WORKSPACES,
) -> list[str]:
    await ensure_bucket(settings)
    base, key = _credentials(settings)
    prefix = f"{user_id}/v76/meta"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"{base}/storage/v1/object/list/{BUCKET}",
            headers=_headers(key, content_type="application/json"),
            json={
                "prefix": prefix,
                "limit": max(1, min(MAX_WORKSPACES, int(limit))),
                "offset": 0,
                "sortBy": {"column": "updated_at", "order": "desc"},
            },
        )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Workspace listing failed ({response.status_code}): "
            f"{response.text[:240]}"
        )
    rows = response.json() if response.content else []
    paths: list[str] = []
    for item in rows if isinstance(rows, list) else []:
        name = str(item.get("name") or "").strip().lstrip("/")
        if not name or not name.endswith(".json"):
            continue
        path = name if name.startswith(f"{user_id}/") else f"{prefix}/{name}"
        paths.append(path)
    return paths


def _public_meta(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(meta.get("id") or ""),
        "title": str(meta.get("title") or "Untitled workspace"),
        "kind": str(meta.get("kind") or "document"),
        "language": str(meta.get("language") or ""),
        "version": int(meta.get("version") or 1),
        "size_bytes": int(meta.get("size_bytes") or 0),
        "created_at": meta.get("created_at"),
        "updated_at": meta.get("updated_at"),
    }


def health_snapshot(settings: Any) -> dict[str, Any]:
    try:
        _credentials(settings)
        persistent = True
    except Exception:
        persistent = False
    return {
        "ok": True,
        "version": "v76",
        "name": "Vasuki Artifacts / Live Workspace",
        "persistent_storage_available": persistent,
        "supported_kinds": sorted(KINDS),
        "features": [
            "persistent-private-workspaces",
            "document-editor",
            "markdown-editor",
            "code-editor",
            "html-live-preview",
            "csv-spreadsheet-preview",
            "version-conflict-protection",
            "client-side-export",
            "create-update-delete",
            "restart-durable-storage",
        ],
        "storage": {
            "backend": "existing-private-supabase-file-library",
            "bucket": BUCKET,
            "namespace": "per-user/v76",
            "generated-artifact-expiry_applies": False,
            "max_workspace_bytes": MAX_CONTENT_BYTES,
            "max_workspaces_per_user": MAX_WORKSPACES,
        },
        "safety": {
            "per_user_ownership": True,
            "html_preview_scripts_enabled": False,
            "external_writes": False,
        },
        "new_database_migration_required": False,
        "new_api_key_required": False,
    }


async def list_workspaces(
    settings: Any,
    *,
    user_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    paths = await _list_meta_paths(
        settings,
        user_id=user_id,
        limit=max(1, min(MAX_WORKSPACES, int(limit))),
    )
    semaphore = asyncio.Semaphore(8)

    async def read_one(path: str) -> dict[str, Any] | None:
        async with semaphore:
            try:
                meta = await _read_json(settings, path=path)
            except Exception:
                return None
            if str(meta.get("user_id") or "") != user_id:
                return None
            return _public_meta(meta)

    items = await asyncio.gather(*(read_one(path) for path in paths))
    result = [item for item in items if isinstance(item, dict)]
    result.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return result[: max(1, min(MAX_WORKSPACES, int(limit)))]


async def create_workspace(
    settings: Any,
    *,
    user_id: str,
    title: str,
    kind: str,
    content: str = "",
    language: str = "",
) -> dict[str, Any]:
    existing = await _list_meta_paths(settings, user_id=user_id, limit=MAX_WORKSPACES)
    if len(existing) >= MAX_WORKSPACES:
        raise ValueError(
            f"Workspace limit reached ({MAX_WORKSPACES}). Delete an old workspace first."
        )

    workspace_id = uuid.uuid4().hex
    clean_kind = _clean_kind(kind)
    clean_title = _clean_title(title)
    clean_language = _clean_language(language)
    body = _content_bytes(content)
    now = _now()
    meta = {
        "version_schema": "v76",
        "id": workspace_id,
        "user_id": user_id,
        "title": clean_title,
        "kind": clean_kind,
        "language": clean_language,
        "version": 1,
        "size_bytes": len(body),
        "created_at": now,
        "updated_at": now,
    }

    content_path = _content_path(user_id, workspace_id)
    meta_path = _meta_path(user_id, workspace_id)
    try:
        await _upload_object(
            settings,
            path=content_path,
            content=body,
            content_type="text/plain; charset=utf-8",
            upsert=False,
        )
        await _upload_object(
            settings,
            path=meta_path,
            content=json.dumps(meta, ensure_ascii=False).encode("utf-8"),
            content_type="application/json",
            upsert=False,
        )
    except Exception:
        try:
            await _delete_paths(settings, paths=[content_path, meta_path])
        except Exception:
            pass
        raise

    return {**_public_meta(meta), "content": body.decode("utf-8")}


async def get_workspace(
    settings: Any,
    *,
    user_id: str,
    workspace_id: str,
) -> dict[str, Any] | None:
    workspace_id = _assert_id(workspace_id)
    try:
        meta = await _read_json(settings, path=_meta_path(user_id, workspace_id))
    except FileNotFoundError:
        return None
    if str(meta.get("user_id") or "") != user_id:
        return None
    try:
        content = (
            await _read_object(settings, path=_content_path(user_id, workspace_id))
        ).decode("utf-8")
    except FileNotFoundError:
        content = ""
    return {**_public_meta(meta), "content": content}


async def update_workspace(
    settings: Any,
    *,
    user_id: str,
    workspace_id: str,
    title: str | None = None,
    kind: str | None = None,
    content: str | None = None,
    language: str | None = None,
    expected_version: int | None = None,
) -> dict[str, Any] | None:
    workspace_id = _assert_id(workspace_id)
    current = await get_workspace(
        settings, user_id=user_id, workspace_id=workspace_id
    )
    if current is None:
        return None

    current_version = int(current.get("version") or 1)
    if expected_version is not None and int(expected_version) != current_version:
        raise WorkspaceConflict(
            f"Workspace changed since you opened it. "
            f"Expected version {expected_version}, current version is {current_version}."
        )

    next_title = _clean_title(title) if title is not None else str(current["title"])
    next_kind = _clean_kind(kind) if kind is not None else str(current["kind"])
    next_language = (
        _clean_language(language) if language is not None else str(current.get("language") or "")
    )
    next_content = str(content) if content is not None else str(current.get("content") or "")
    body = _content_bytes(next_content)
    meta = {
        "version_schema": "v76",
        "id": workspace_id,
        "user_id": user_id,
        "title": next_title,
        "kind": next_kind,
        "language": next_language,
        "version": current_version + 1,
        "size_bytes": len(body),
        "created_at": current.get("created_at") or _now(),
        "updated_at": _now(),
    }

    await _upload_object(
        settings,
        path=_content_path(user_id, workspace_id),
        content=body,
        content_type="text/plain; charset=utf-8",
        upsert=True,
    )
    await _upload_object(
        settings,
        path=_meta_path(user_id, workspace_id),
        content=json.dumps(meta, ensure_ascii=False).encode("utf-8"),
        content_type="application/json",
        upsert=True,
    )
    return {**_public_meta(meta), "content": next_content}


async def delete_workspace(
    settings: Any,
    *,
    user_id: str,
    workspace_id: str,
) -> bool:
    workspace_id = _assert_id(workspace_id)
    current = await get_workspace(
        settings, user_id=user_id, workspace_id=workspace_id
    )
    if current is None:
        return False
    await _delete_paths(
        settings,
        paths=[
            _meta_path(user_id, workspace_id),
            _content_path(user_id, workspace_id),
        ],
    )
    return True
