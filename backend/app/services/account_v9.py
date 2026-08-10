from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.auth import AuthUser
from app.config import Settings
from app.services.analytics_v8 import _base, _headers, configured
from app.services.artifacts_v8 import delete_artifact, list_artifacts
from app.services.plans_v2 import get_plan_status


EXPORT_TABLES = [
    "user_chats",
    "user_chat_messages",
    "user_memories",
    "user_documents",
    "user_document_chunks",
    "projects",
    "project_memories",
    "response_feedback",
    "conversation_branches",
    "generated_artifacts",
    "usage_events",
    "user_daily_usage",
    "user_daily_puter_images",
    "user_plans",
    "payment_orders",
    "project_files_v9",
    "project_file_versions_v9",
    "background_jobs_v9",
    "notifications_v9",
    "experiment_events_v9",
    "push_subscriptions_v9",
]

DELETE_TABLES = [
    "user_chat_messages",
    "project_file_versions_v9",
    "project_files_v9",
    "project_memories",
    "conversation_branches",
    "response_feedback",
    "user_document_chunks",
    "user_documents",
    "background_jobs_v9",
    "notifications_v9",
    "experiment_events_v9",
    "push_subscriptions_v9",
    "usage_events",
    "user_daily_usage",
    "user_daily_puter_images",
    "payment_orders",
    "user_plans",
    "user_memories",
    "generated_artifacts",
    "user_chats",
    "projects",
]

_REDACT_KEYS = {
    "embedding",
    "signature",
    "access_token",
    "refresh_token",
    "password",
    "secret",
}


def _sanitize(value: Any) -> Any:
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _sanitize(item)
        for key, item in value.items()
        if str(key).casefold() not in _REDACT_KEYS
    }


async def _rows(
    settings: Settings,
    *,
    table: str,
    user_id: str,
    max_rows: int = 50000,
) -> list[dict[str, Any]]:
    if not configured(settings):
        return []
    output: list[dict[str, Any]] = []
    offset = 0
    page = 1000
    while offset < max_rows:
        url = (
            f"{_base(settings)}/rest/v1/{table}"
            f"?user_id=eq.{quote(user_id)}"
            f"&select=*&limit={page}&offset={offset}"
        )
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers=_headers(settings))
        if response.status_code in {400, 404}:
            break
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or not rows:
            break
        output.extend(_sanitize(rows))
        if len(rows) < page:
            break
        offset += page
    return output


async def list_user_chats(
    settings: Settings,
    *,
    user_id: str,
    limit: int = 200,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 500))
    url = (
        f"{_base(settings)}/rest/v1/user_chats"
        f"?user_id=eq.{quote(user_id)}"
        "&select=id,title,updated_at,project_id"
        "&order=updated_at.desc"
        f"&limit={safe_limit}"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=_headers(settings))
    response.raise_for_status()
    rows = response.json()
    return rows if isinstance(rows, list) else []


async def export_chat(
    settings: Settings,
    *,
    user_id: str,
    chat_id: str,
    export_format: str,
) -> dict[str, Any]:
    chat_url = (
        f"{_base(settings)}/rest/v1/user_chats"
        f"?id=eq.{quote(chat_id)}&user_id=eq.{quote(user_id)}"
        "&select=id,title,updated_at,project_id&limit=1"
    )
    messages_url = (
        f"{_base(settings)}/rest/v1/user_chat_messages"
        f"?chat_id=eq.{quote(chat_id)}&user_id=eq.{quote(user_id)}"
        "&select=role,content,image_url,file_name,provider,sources,position,created_at"
        "&order=position.asc&limit=5000"
    )
    async with httpx.AsyncClient(timeout=12.0) as client:
        chat_response, messages_response = await asyncio.gather(
            client.get(chat_url, headers=_headers(settings)),
            client.get(messages_url, headers=_headers(settings)),
        )
    chat_response.raise_for_status()
    messages_response.raise_for_status()
    chats = chat_response.json()
    if not isinstance(chats, list) or not chats:
        raise ValueError("Chat not found.")
    chat = chats[0]
    messages = messages_response.json()
    messages = messages if isinstance(messages, list) else []
    safe_title = str(chat.get("title") or "Vasuki AI chat").strip()[:120]

    if export_format == "json":
        content = json.dumps(
            {
                "chat": chat,
                "messages": _sanitize(messages),
                "exported_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        return {
            "filename": f"{safe_title}.json",
            "mime_type": "application/json",
            "content": content,
        }

    lines = [f"# {safe_title}", ""]
    for row in messages:
        role = "You" if str(row.get("role")) == "user" else "Vasuki AI"
        lines.extend([f"## {role}", "", str(row.get("content") or "").strip(), ""])
        file_name = str(row.get("file_name") or "").strip()
        if file_name:
            lines.extend([f"_File: {file_name}_", ""])
        sources = row.get("sources")
        if isinstance(sources, list) and sources:
            lines.append("Sources:")
            for source in sources[:20]:
                if not isinstance(source, dict):
                    continue
                title = str(source.get("title") or source.get("domain") or "Source")
                url = str(source.get("url") or "")
                lines.append(f"- {title}" + (f": {url}" if url else ""))
            lines.append("")
    return {
        "filename": f"{safe_title}.md",
        "mime_type": "text/markdown",
        "content": "\n".join(lines).strip() + "\n",
    }


async def full_account_export(
    settings: Settings,
    *,
    current_user: AuthUser,
) -> dict[str, Any]:
    tables: dict[str, Any] = {}
    warnings: list[str] = []
    for table in EXPORT_TABLES:
        try:
            tables[table] = await _rows(
                settings,
                table=table,
                user_id=current_user.id,
            )
        except Exception as exc:
            tables[table] = []
            warnings.append(f"{table}: {str(exc)[:240]}")
    return {
        "schema": "vasuki-account-export-v9-phase5",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account": {
            "user_id": current_user.id,
            "email": current_user.email,
        },
        "tables": tables,
        "redacted_fields": sorted(_REDACT_KEYS),
        "warnings": warnings,
    }


def validate_delete_confirmation(
    *,
    account_email: str | None,
    confirm_email: str,
    confirmation: str,
) -> None:
    if confirmation.strip() != "DELETE MY ACCOUNT":
        raise ValueError('Type exactly "DELETE MY ACCOUNT".')
    expected = str(account_email or "").strip().casefold()
    if not expected or confirm_email.strip().casefold() != expected:
        raise ValueError("Account email confirmation does not match.")


async def delete_account(
    settings: Settings,
    *,
    current_user: AuthUser,
    confirm_email: str,
    confirmation: str,
) -> dict[str, Any]:
    validate_delete_confirmation(
        account_email=current_user.email,
        confirm_email=confirm_email,
        confirmation=confirmation,
    )
    status = await get_plan_status(current_user, settings)
    if status.is_owner:
        raise ValueError("Owner account deletion is blocked from the self-service API.")
    if not configured(settings):
        raise RuntimeError("Supabase admin access is not configured.")

    key = settings.supabase_secret_key or settings.supabase_service_role_key or ""
    auth_headers = {"apikey": key}
    if key:
        auth_headers["Authorization"] = f"Bearer {key}"

    # Preflight admin permission before any destructive data cleanup.
    async with httpx.AsyncClient(timeout=10.0) as client:
        preflight = await client.get(
            f"{_base(settings)}/auth/v1/admin/users/{quote(current_user.id)}",
            headers=auth_headers,
        )
    if not preflight.is_success:
        raise RuntimeError(
            f"Account deletion preflight failed ({preflight.status_code}). No data was deleted."
        )

    artifact_deleted = 0
    for _round in range(20):
        artifacts = await list_artifacts(settings, current_user.id, limit=200)
        if not artifacts:
            break
        deleted_this_round = 0
        for artifact in artifacts:
            try:
                if await delete_artifact(
                    settings,
                    current_user.id,
                    str(artifact.get("id") or ""),
                ):
                    artifact_deleted += 1
                    deleted_this_round += 1
            except Exception:
                continue
        if deleted_this_round == 0:
            break

    deleted_tables: list[str] = []
    warnings: list[str] = []
    if configured(settings):
        async with httpx.AsyncClient(timeout=15.0) as client:
            for table in DELETE_TABLES:
                url = (
                    f"{_base(settings)}/rest/v1/{table}"
                    f"?user_id=eq.{quote(current_user.id)}"
                )
                try:
                    response = await client.delete(url, headers=_headers(settings))
                    if response.status_code in {200, 204}:
                        deleted_tables.append(table)
                    elif response.status_code not in {400, 404}:
                        warnings.append(f"{table}: HTTP {response.status_code}")
                except Exception as exc:
                    warnings.append(f"{table}: {str(exc)[:160]}")

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.delete(
            f"{_base(settings)}/auth/v1/admin/users/{quote(current_user.id)}",
            headers=auth_headers,
        )
    if not response.is_success:
        raise RuntimeError(
            f"Account content cleanup ran, but Auth user deletion failed ({response.status_code})."
        )

    return {
        "ok": True,
        "artifact_files_deleted": artifact_deleted,
        "tables_deleted": deleted_tables,
        "warnings": warnings,
    }
