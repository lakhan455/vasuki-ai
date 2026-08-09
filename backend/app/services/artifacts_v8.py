from __future__ import annotations

import base64
import mimetypes
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.services.analytics_v8 import _base, _headers, configured

BUCKET = "vasuki-artifacts"


def _decode_data_url(data_url: str) -> tuple[str, bytes] | None:
    match = re.match(r"^data:([^;,]+);base64,(.+)$", str(data_url or ""), re.S)
    if not match:
        return None
    try:
        return match.group(1), base64.b64decode(match.group(2))
    except Exception:
        return None


def _ext_for_mime(mime: str) -> str:
    known = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "text/plain": ".txt",
    }
    return known.get(mime, mimetypes.guess_extension(mime) or ".bin")


async def _upload_bytes(
    settings: Settings,
    *,
    storage_path: str,
    mime_type: str,
    content: bytes,
) -> bool:
    if not configured(settings):
        return False
    url = f"{_base(settings)}/storage/v1/object/{BUCKET}/{quote(storage_path, safe='/')}"
    headers = {
        **_headers(settings),
        "Content-Type": mime_type,
        "x-upsert": "false",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, content=content)
        return response.is_success
    except Exception:
        return False


async def save_artifact(
    settings: Settings,
    *,
    user_id: str,
    name: str,
    artifact_type: str,
    mime_type: str,
    data_url: str | None = None,
    external_url: str | None = None,
    prompt: str | None = None,
    provider: str | None = None,
    retention_days: int = 30,
) -> dict[str, Any] | None:
    if not configured(settings):
        return None

    artifact_id = str(uuid.uuid4())
    storage_path = None
    size_bytes = None
    decoded = _decode_data_url(data_url or "")
    if decoded:
        decoded_mime, content = decoded
        mime_type = decoded_mime or mime_type
        ext = _ext_for_mime(mime_type)
        storage_path = f"{user_id}/{artifact_type}/{artifact_id}{ext}"
        if await _upload_bytes(
            settings,
            storage_path=storage_path,
            mime_type=mime_type,
            content=content,
        ):
            size_bytes = len(content)
        else:
            storage_path = None

    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=max(7, min(int(retention_days), 30)))
    ).isoformat()
    payload = {
        "id": artifact_id,
        "user_id": user_id,
        "name": str(name or "Vasuki AI file")[:240],
        "artifact_type": str(artifact_type or "file")[:50],
        "mime_type": str(mime_type or "application/octet-stream")[:150],
        "storage_path": storage_path,
        "external_url": external_url if external_url and external_url.startswith("http") else None,
        "size_bytes": size_bytes,
        "prompt": str(prompt or "")[:5000] or None,
        "provider": str(provider or "")[:80] or None,
        "expires_at": expires_at,
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                f"{_base(settings)}/rest/v1/generated_artifacts",
                headers=_headers(settings, representation=True),
                json=payload,
            )
        if response.is_success:
            rows = response.json()
            if isinstance(rows, list) and rows:
                return rows[0]
    except Exception:
        pass
    return payload


async def signed_url(settings: Settings, storage_path: str, expires_in: int = 3600) -> str:
    if not storage_path:
        return ""
    url = f"{_base(settings)}/storage/v1/object/sign/{BUCKET}/{quote(storage_path, safe='/')}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                url, headers=_headers(settings), json={"expiresIn": int(expires_in)}
            )
        if response.is_success:
            value = str((response.json() or {}).get("signedURL") or "")
            if value.startswith("http"):
                return value
            if value:
                return f"{_base(settings)}/storage/v1{value}"
    except Exception:
        pass
    return ""


async def list_artifacts(settings: Settings, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 200))
    url = (
        f"{_base(settings)}/rest/v1/generated_artifacts"
        f"?user_id=eq.{quote(user_id)}"
        "&select=id,name,artifact_type,mime_type,storage_path,external_url,size_bytes,prompt,provider,created_at,expires_at"
        "&order=created_at.desc"
        f"&limit={safe_limit}"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=_headers(settings))
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            return []
        for row in rows:
            if row.get("storage_path"):
                row["download_url"] = await signed_url(settings, str(row["storage_path"]))
            elif row.get("external_url"):
                row["download_url"] = row["external_url"]
            else:
                row["download_url"] = ""
        return rows
    except Exception:
        return []


async def delete_artifact(settings: Settings, user_id: str, artifact_id: str) -> bool:
    rows_url = (
        f"{_base(settings)}/rest/v1/generated_artifacts"
        f"?id=eq.{quote(artifact_id)}&user_id=eq.{quote(user_id)}"
        "&select=id,storage_path&limit=1"
    )
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(rows_url, headers=_headers(settings))
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or not rows:
            return False
        storage_path = str(rows[0].get("storage_path") or "")
        if storage_path:
            await client.delete(
                f"{_base(settings)}/storage/v1/object/{BUCKET}/{quote(storage_path, safe='/')}",
                headers=_headers(settings),
            )
        delete_url = (
            f"{_base(settings)}/rest/v1/generated_artifacts"
            f"?id=eq.{quote(artifact_id)}&user_id=eq.{quote(user_id)}"
        )
        deleted = await client.delete(delete_url, headers=_headers(settings))
        return deleted.is_success


async def cleanup_expired(settings: Settings, *, limit: int = 100) -> int:
    now = datetime.now(timezone.utc).isoformat()
    url = (
        f"{_base(settings)}/rest/v1/generated_artifacts"
        f"?expires_at=lt.{quote(now)}&select=id,user_id,storage_path&limit={max(1, min(limit, 200))}"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=_headers(settings))
        if not response.is_success:
            return 0
        rows = response.json()
        count = 0
        for row in rows if isinstance(rows, list) else []:
            if await delete_artifact(settings, str(row["user_id"]), str(row["id"])):
                count += 1
        return count
    except Exception:
        return 0
