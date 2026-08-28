from __future__ import annotations

import re
import uuid
from typing import Any

import httpx

BUCKET = "vasuki-files-v48"
MAX_FILE_BYTES = 20 * 1024 * 1024


def _credentials(settings: Any) -> tuple[str, str]:
    url = str(getattr(settings, "supabase_url", "") or "").strip().rstrip("/")
    key = str(
        getattr(settings, "supabase_service_role_key", None)
        or getattr(settings, "supabase_secret_key", None)
        or ""
    ).strip()
    if not url or not key:
        raise RuntimeError("Supabase backend credentials are required for the V48 file library.")
    return url, key


def _headers(key: str, *, content_type: str | None = None) -> dict[str, str]:
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _safe_filename(name: str) -> str:
    raw = (name or "file").strip().replace("\\", "_").replace("/", "_")
    safe = re.sub(r"[^A-Za-z0-9._() -]+", "_", raw).strip(" .")
    return (safe or "file")[:180]


async def ensure_bucket(settings: Any) -> None:
    base, key = _credentials(settings)
    async with httpx.AsyncClient(timeout=10.0) as client:
        check = await client.get(f"{base}/storage/v1/bucket/{BUCKET}", headers=_headers(key))
        if check.status_code == 200:
            return
        create = await client.post(
            f"{base}/storage/v1/bucket",
            headers=_headers(key, content_type="application/json"),
            json={"id": BUCKET, "name": BUCKET, "public": False, "file_size_limit": MAX_FILE_BYTES},
        )
        if create.status_code not in {200, 201, 409}:
            raise RuntimeError(f"Could not initialize file library ({create.status_code}): {create.text[:300]}")


async def upload_file(settings: Any, *, user_id: str, filename: str, content_type: str, data: bytes) -> dict[str, Any]:
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("File exceeds the 20 MB V48 library limit.")
    await ensure_bucket(settings)
    base, key = _credentials(settings)
    safe = _safe_filename(filename)
    object_path = f"{user_id}/{uuid.uuid4().hex}-{safe}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{base}/storage/v1/object/{BUCKET}/{object_path}",
            headers={**_headers(key, content_type=content_type or "application/octet-stream"), "x-upsert": "false"},
            content=data,
        )
    if response.status_code not in {200, 201}:
        raise RuntimeError(f"File upload failed ({response.status_code}): {response.text[:300]}")
    return {
        "name": safe,
        "path": object_path,
        "size": len(data),
        "content_type": content_type or "application/octet-stream",
    }


async def list_files(settings: Any, *, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
    await ensure_bucket(settings)
    base, key = _credentials(settings)
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{base}/storage/v1/object/list/{BUCKET}",
            headers=_headers(key, content_type="application/json"),
            json={
                "prefix": user_id,
                "limit": max(1, min(200, int(limit))),
                "offset": 0,
                "sortBy": {"column": "created_at", "order": "desc"},
            },
        )
    if response.status_code >= 400:
        raise RuntimeError(f"File library listing failed ({response.status_code}): {response.text[:300]}")
    rows = response.json() if response.content else []
    output: list[dict[str, Any]] = []
    for item in rows if isinstance(rows, list) else []:
        name = str(item.get("name") or "")
        path = name if name.startswith(f"{user_id}/") else f"{user_id}/{name}"
        output.append({
            "name": name.split("-", 1)[-1] if "-" in name else name,
            "path": path,
            "id": item.get("id"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "metadata": item.get("metadata") or {},
        })
    return output


def _assert_owned(user_id: str, path: str) -> str:
    value = str(path or "").lstrip("/")
    if not value.startswith(f"{user_id}/"):
        raise PermissionError("File does not belong to the current user.")
    return value


async def signed_download_url(settings: Any, *, user_id: str, path: str, expires_seconds: int = 900) -> str:
    value = _assert_owned(user_id, path)
    base, key = _credentials(settings)
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.post(
            f"{base}/storage/v1/object/sign/{BUCKET}/{value}",
            headers=_headers(key, content_type="application/json"),
            json={"expiresIn": max(60, min(3600, int(expires_seconds)))},
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Could not create download link ({response.status_code}): {response.text[:300]}")
    payload = response.json()
    signed = str(payload.get("signedURL") or payload.get("signedUrl") or "")
    if not signed:
        raise RuntimeError("Supabase did not return a signed file URL.")
    return signed if signed.startswith("http") else f"{base}/storage/v1{signed}"


async def delete_file(settings: Any, *, user_id: str, path: str) -> bool:
    value = _assert_owned(user_id, path)
    base, key = _credentials(settings)
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.request(
            "DELETE",
            f"{base}/storage/v1/object/{BUCKET}",
            headers=_headers(key, content_type="application/json"),
            json={"prefixes": [value]},
        )
    if response.status_code >= 400:
        raise RuntimeError(f"File deletion failed ({response.status_code}): {response.text[:300]}")
    return True
