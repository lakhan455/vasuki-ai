from __future__ import annotations

import json
import re
import uuid
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.services.analytics_v8 import _base, _headers, configured


def normalize_project_name(name: str) -> str:
    clean = re.sub(r"\s+", " ", str(name or "")).strip()
    return clean[:120]


async def list_projects(settings: Settings, user_id: str) -> list[dict[str, Any]]:
    if not configured(settings):
        return []
    url = (
        f"{_base(settings)}/rest/v1/projects"
        f"?user_id=eq.{quote(user_id)}"
        "&select=id,name,description,instructions,color,archived,created_at,updated_at"
        "&order=updated_at.desc"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=_headers(settings))
    response.raise_for_status()
    rows = response.json()
    return rows if isinstance(rows, list) else []


async def create_project(
    settings: Settings,
    *,
    user_id: str,
    name: str,
    description: str | None = None,
    instructions: str | None = None,
    color: str | None = None,
) -> dict[str, Any]:
    if not configured(settings):
        raise RuntimeError('Supabase is not configured.')
    payload = {
        'id': str(uuid.uuid4()),
        'user_id': user_id,
        'name': normalize_project_name(name),
        'description': str(description or '')[:2000] or None,
        'instructions': str(instructions or '')[:12000] or None,
        'color': str(color or '#8b5cf6')[:20],
        'archived': False,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{_base(settings)}/rest/v1/projects",
            headers=_headers(settings, representation=True),
            json=payload,
        )
    response.raise_for_status()
    rows = response.json()
    if isinstance(rows, list) and rows:
        return rows[0]
    return payload


async def update_project(
    settings: Settings,
    *,
    user_id: str,
    project_id: str,
    patch: dict[str, Any],
) -> dict[str, Any] | None:
    if not configured(settings):
        return None
    allowed = {
        'name': normalize_project_name(str(patch.get('name') or '')) if 'name' in patch else None,
        'description': str(patch.get('description') or '')[:2000] if 'description' in patch else None,
        'instructions': str(patch.get('instructions') or '')[:12000] if 'instructions' in patch else None,
        'color': str(patch.get('color') or '')[:20] if 'color' in patch else None,
        'archived': bool(patch.get('archived')) if 'archived' in patch else None,
    }
    data = {k: v for k, v in allowed.items() if v is not None}
    if not data:
        return None
    url = (
        f"{_base(settings)}/rest/v1/projects"
        f"?id=eq.{quote(project_id)}&user_id=eq.{quote(user_id)}"
    )
    headers = {**_headers(settings, representation=True), 'Prefer': 'return=representation'}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.patch(url, headers=headers, json=data)
    response.raise_for_status()
    rows = response.json()
    if isinstance(rows, list) and rows:
        return rows[0]
    return None


async def delete_project(settings: Settings, *, user_id: str, project_id: str) -> bool:
    if not configured(settings):
        return False
    url = (
        f"{_base(settings)}/rest/v1/projects"
        f"?id=eq.{quote(project_id)}&user_id=eq.{quote(user_id)}"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.delete(url, headers=_headers(settings))
    return response.is_success
