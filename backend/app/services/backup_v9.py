from __future__ import annotations

import base64
import gzip
import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.services.analytics_v8 import _base, _headers, configured

BACKUP_TABLES = [
    "feature_flags_v9", "user_plans", "projects", "user_chats", "user_memories",
    "user_documents", "project_files_v9", "project_memories", "user_chat_messages",
    "user_document_chunks", "project_file_versions_v9",
]
RESTORE_ORDER = list(BACKUP_TABLES)
MAX_ROWS_PER_TABLE = 20000
MAX_COMPRESSED_BYTES = 15 * 1024 * 1024


async def _read_table(settings: Settings, table: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    offset = 0
    page = 1000
    while offset < MAX_ROWS_PER_TABLE:
        url = f"{_base(settings)}/rest/v1/{table}?select=*&limit={page}&offset={offset}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=_headers(settings))
        if response.status_code in {400, 404}:
            return output
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or not rows:
            break
        output.extend(rows)
        if len(rows) < page:
            break
        offset += page
    return output


async def create_backup(settings: Settings, *, owner_user_id: str, note: str = "") -> dict[str, Any]:
    if not configured(settings):
        raise RuntimeError("Supabase server credentials are required.")
    tables: dict[str, list[dict[str, Any]]] = {}
    warnings: list[str] = []
    for table in BACKUP_TABLES:
        try:
            tables[table] = await _read_table(settings, table)
        except Exception as exc:
            tables[table] = []
            warnings.append(f"{table}: {str(exc)[:220]}")
    package = {
        "schema": "vasuki-v9-phase6-logical-backup",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tables": tables,
        "limitations": ["Supabase Auth identities are not included.", "Storage object bytes are not included.", "Restore requires referenced auth.users rows to still exist."],
    }
    raw = json.dumps(package, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    compressed = gzip.compress(raw, compresslevel=9)
    if len(compressed) > MAX_COMPRESSED_BYTES:
        raise ValueError("Application backup is larger than 15 MB compressed. Use Supabase native database/storage backups for a full disaster-recovery snapshot.")
    digest = hashlib.sha256(compressed).hexdigest()
    payload = {
        "created_by": owner_user_id,
        "note": str(note or "")[:1000],
        "schema_version": package["schema"],
        "sha256": digest,
        "compressed_bytes": len(compressed),
        "table_counts": {key: len(value) for key, value in tables.items()},
        "warnings": warnings,
        "payload_b64": base64.b64encode(compressed).decode("ascii"),
    }
    headers = dict(_headers(settings)); headers["Prefer"] = "return=representation"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(f"{_base(settings)}/rest/v1/app_backups_v9", headers=headers, json=payload)
    response.raise_for_status()
    rows = response.json(); row = rows[0] if isinstance(rows, list) and rows else payload
    row.pop("payload_b64", None)
    return row


async def list_backups(settings: Settings, *, limit: int = 30) -> list[dict[str, Any]]:
    if not configured(settings): return []
    url = f"{_base(settings)}/rest/v1/app_backups_v9?select=id,created_by,note,schema_version,sha256,compressed_bytes,table_counts,warnings,created_at&order=created_at.desc&limit={max(1, min(limit, 100))}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=_headers(settings))
    if response.status_code in {400, 404}: return []
    response.raise_for_status(); rows = response.json()
    return rows if isinstance(rows, list) else []


async def _backup_payload(settings: Settings, backup_id: str) -> dict[str, Any]:
    url = f"{_base(settings)}/rest/v1/app_backups_v9?id=eq.{quote(backup_id)}&select=id,schema_version,sha256,payload_b64&limit=1"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, headers=_headers(settings))
    response.raise_for_status(); rows = response.json()
    if not isinstance(rows, list) or not rows: raise ValueError("Backup not found.")
    row = rows[0]; compressed = base64.b64decode(str(row.get("payload_b64") or ""))
    if hashlib.sha256(compressed).hexdigest() != str(row.get("sha256") or ""): raise ValueError("Backup integrity verification failed.")
    package = json.loads(gzip.decompress(compressed).decode("utf-8"))
    if package.get("schema") != "vasuki-v9-phase6-logical-backup": raise ValueError("Unsupported backup schema.")
    return package


async def restore_backup(settings: Settings, *, backup_id: str, apply: bool, confirmation: str) -> dict[str, Any]:
    package = await _backup_payload(settings, backup_id)
    tables = package.get("tables") if isinstance(package.get("tables"), dict) else {}
    counts = {table: len(tables.get(table) or []) for table in RESTORE_ORDER}
    if not apply:
        return {"ok": True, "dry_run": True, "table_counts": counts, "limitations": package.get("limitations") or []}
    if confirmation.strip() != "RESTORE VASUKI BACKUP": raise ValueError('Type exactly "RESTORE VASUKI BACKUP" to apply a restore.')
    restored: dict[str, int] = {}; errors: dict[str, str] = {}
    for table in RESTORE_ORDER:
        rows = tables.get(table)
        if not isinstance(rows, list) or not rows:
            restored[table] = 0; continue
        try:
            headers = dict(_headers(settings)); headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
            async with httpx.AsyncClient(timeout=30.0) as client:
                for start in range(0, len(rows), 250):
                    response = await client.post(f"{_base(settings)}/rest/v1/{table}", headers=headers, json=rows[start:start + 250])
                    response.raise_for_status()
            restored[table] = len(rows)
        except Exception as exc:
            errors[table] = str(exc)[:500]
    return {"ok": not errors, "dry_run": False, "restored": restored, "errors": errors, "note": "Application-level restore is best-effort and not atomic. Auth users and storage object bytes are outside this backup."}
