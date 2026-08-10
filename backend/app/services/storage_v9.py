from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.services.analytics_v8 import _base, _headers, configured


DEFAULT_STORAGE_QUOTAS = {
    "free": 250 * 1024 * 1024,
    "pro": 2 * 1024 * 1024 * 1024,
    "owner": 20 * 1024 * 1024 * 1024,
}


class StorageQuotaExceeded(ValueError):
    pass


def _quota_config() -> dict[str, int]:
    quotas = dict(DEFAULT_STORAGE_QUOTAS)
    raw = os.getenv("VASUKI_STORAGE_QUOTAS_JSON", "").strip()
    if not raw:
        return quotas
    try:
        value = json.loads(raw)
    except Exception:
        return quotas
    if not isinstance(value, dict):
        return quotas
    for key in ("free", "pro", "owner"):
        try:
            parsed = int(value.get(key))
        except Exception:
            continue
        if parsed > 0:
            quotas[key] = parsed
    return quotas


async def _auth_email(settings: Settings, user_id: str) -> str:
    if not configured(settings):
        return ""
    key = settings.supabase_secret_key or settings.supabase_service_role_key or ""
    headers = {"apikey": key}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                f"{_base(settings)}/auth/v1/admin/users/{quote(user_id)}",
                headers=headers,
            )
        if not response.is_success:
            return ""
        return str((response.json() or {}).get("email") or "").strip().casefold()
    except Exception:
        return ""


async def resolve_storage_plan(settings: Settings, user_id: str) -> str:
    owner_emails = {
        item.strip().casefold()
        for item in str(settings.vasuki_owner_emails or "").split(",")
        if item.strip()
    }
    email = await _auth_email(settings, user_id)
    if email and email in owner_emails:
        return "owner"

    if not configured(settings):
        return "free"
    try:
        url = (
            f"{_base(settings)}/rest/v1/user_plans"
            f"?user_id=eq.{quote(user_id)}"
            "&select=plan,pro_expires_at&limit=1"
        )
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(url, headers=_headers(settings))
        if not response.is_success:
            return "free"
        rows = response.json()
        if not isinstance(rows, list) or not rows:
            return "free"
        row = rows[0]
        if str(row.get("plan") or "").casefold() != "pro":
            return "free"
        expires = str(row.get("pro_expires_at") or "")
        if not expires:
            return "free"
        parsed = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc):
            return "pro"
    except Exception:
        return "free"
    return "free"


async def _sum_table(
    settings: Settings,
    *,
    table: str,
    user_id: str,
    field: str = "size_bytes",
) -> int:
    if not configured(settings):
        return 0
    total = 0
    offset = 0
    page = 1000
    while offset < 10000:
        url = (
            f"{_base(settings)}/rest/v1/{table}"
            f"?user_id=eq.{quote(user_id)}"
            f"&select={field}&limit={page}&offset={offset}"
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=_headers(settings))
            if response.status_code in {400, 404}:
                return total
            response.raise_for_status()
            rows = response.json()
        except Exception:
            return total
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            try:
                total += max(0, int(row.get(field) or 0))
            except Exception:
                continue
        if len(rows) < page:
            break
        offset += page
    return total


async def storage_usage(settings: Settings, user_id: str) -> dict[str, Any]:
    if configured(settings):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{_base(settings)}/rest/v1/rpc/storage_usage_v9",
                    headers=_headers(settings),
                    json={"p_user_id": user_id},
                )
            if response.is_success:
                rows = response.json()
                if isinstance(rows, list) and rows:
                    row = rows[0]
                    artifact_bytes = int(row.get("artifact_bytes") or 0)
                    document_bytes = int(row.get("document_bytes") or 0)
                    project_bytes = int(row.get("project_bytes") or 0)
                    used_bytes = artifact_bytes + document_bytes + project_bytes
                    plan = await resolve_storage_plan(settings, user_id)
                    quota = _quota_config()[plan]
                    return {
                        "plan": plan,
                        "quota_bytes": quota,
                        "used_bytes": used_bytes,
                        "remaining_bytes": max(0, quota - used_bytes),
                        "percent_used": round((used_bytes / quota) * 100, 2) if quota else 0,
                        "breakdown": {
                            "generated_artifacts": artifact_bytes,
                            "knowledge_documents": document_bytes,
                            "project_files": project_bytes,
                        },
                    }
        except Exception:
            pass

    artifact_bytes = await _sum_table(settings, table="generated_artifacts", user_id=user_id)
    document_bytes = await _sum_table(settings, table="user_documents", user_id=user_id)
    project_bytes = await _sum_table(settings, table="project_files_v9", user_id=user_id)
    used_bytes = artifact_bytes + document_bytes + project_bytes
    plan = await resolve_storage_plan(settings, user_id)
    quota = _quota_config()[plan]
    return {
        "plan": plan,
        "quota_bytes": quota,
        "used_bytes": used_bytes,
        "remaining_bytes": max(0, quota - used_bytes),
        "percent_used": round((used_bytes / quota) * 100, 2) if quota else 0,
        "breakdown": {
            "generated_artifacts": artifact_bytes,
            "knowledge_documents": document_bytes,
            "project_files": project_bytes,
        },
    }


async def ensure_storage_quota(
    settings: Settings,
    user_id: str,
    *,
    incoming_bytes: int,
) -> dict[str, Any]:
    incoming = max(0, int(incoming_bytes))
    snapshot = await storage_usage(settings, user_id)
    if int(snapshot["used_bytes"]) + incoming > int(snapshot["quota_bytes"]):
        raise StorageQuotaExceeded(
            "Storage quota exceeded. Delete old generated files/documents or upgrade the plan."
        )
    return snapshot


async def cleanup_user_expired_artifacts(
    settings: Settings,
    *,
    user_id: str,
    limit: int = 200,
) -> dict[str, Any]:
    if not configured(settings):
        return {"deleted": 0}
    now = datetime.now(timezone.utc).isoformat()
    url = (
        f"{_base(settings)}/rest/v1/generated_artifacts"
        f"?user_id=eq.{quote(user_id)}"
        f"&expires_at=lt.{quote(now)}"
        "&select=id,user_id&order=expires_at.asc"
        f"&limit={max(1, min(int(limit), 500))}"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=_headers(settings))
    if not response.is_success:
        return {"deleted": 0}
    rows = response.json()
    deleted = 0
    for row in rows if isinstance(rows, list) else []:
        artifact_id = str(row.get("id") or "")
        if not artifact_id:
            continue
        detail_url = (
            f"{_base(settings)}/rest/v1/generated_artifacts"
            f"?id=eq.{quote(artifact_id)}&user_id=eq.{quote(user_id)}"
            "&select=id,storage_path&limit=1"
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            detail = await client.get(detail_url, headers=_headers(settings))
            detail_rows = detail.json() if detail.is_success else []
            storage_path = ""
            if isinstance(detail_rows, list) and detail_rows:
                storage_path = str(detail_rows[0].get("storage_path") or "")
            if storage_path:
                await client.delete(
                    f"{_base(settings)}/storage/v1/object/vasuki-artifacts/{quote(storage_path, safe='/')}",
                    headers=_headers(settings),
                )
            removed = await client.delete(
                (
                    f"{_base(settings)}/rest/v1/generated_artifacts"
                    f"?id=eq.{quote(artifact_id)}&user_id=eq.{quote(user_id)}"
                ),
                headers=_headers(settings),
            )
            if removed.is_success:
                deleted += 1
    return {"deleted": deleted}
