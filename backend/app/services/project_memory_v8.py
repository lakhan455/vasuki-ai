from __future__ import annotations

import re
import uuid
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.services import personal_memory as personal
from app.services import rag
from app.services.analytics_v8 import _base, _headers, configured


def normalize_project_memory(value: str) -> str:
    clean = re.sub(r"\s+", " ", str(value or "")).strip()
    return clean.casefold()


def _lexical_score(query: str, text: str) -> float:
    q = {token for token in re.findall(r"[\w-]+", query.casefold()) if len(token) > 2}
    t = {token for token in re.findall(r"[\w-]+", text.casefold()) if len(token) > 2}
    if not q or not t:
        return 0.0
    overlap = len(q & t) / max(1, len(q))
    phrase = 0.35 if query.casefold() in text.casefold() else 0.0
    return min(1.0, overlap + phrase)


async def get_project(
    settings: Settings,
    *,
    user_id: str,
    project_id: str,
) -> dict[str, Any] | None:
    if not configured(settings):
        return None
    url = (
        f"{_base(settings)}/rest/v1/projects"
        f"?id=eq.{quote(project_id)}&user_id=eq.{quote(user_id)}"
        "&select=id,name,description,instructions,color,archived,created_at,updated_at"
        "&limit=1"
    )
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(url, headers=_headers(settings))
    response.raise_for_status()
    rows = response.json()
    return rows[0] if isinstance(rows, list) and rows else None


async def list_project_memories(
    settings: Settings,
    *,
    user_id: str,
    project_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if not configured(settings):
        return []
    safe_limit = max(1, min(int(limit), 200))
    url = (
        f"{_base(settings)}/rest/v1/project_memories"
        f"?user_id=eq.{quote(user_id)}&project_id=eq.{quote(project_id)}"
        "&select=id,project_id,memory_text,normalized_text,source,confidence,created_at,updated_at"
        "&order=updated_at.desc"
        f"&limit={safe_limit}"
    )
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(url, headers=_headers(settings))
    if response.status_code in {400, 404}:
        return []
    response.raise_for_status()
    rows = response.json()
    return rows if isinstance(rows, list) else []


async def _embed(text: str, settings: Settings) -> list[float] | None:
    if not settings.google_gemini_api:
        return None
    try:
        vectors = await rag._embed_batch(
            [text[:12000]],
            settings,
            task_type="RETRIEVAL_DOCUMENT",
            title="Project memory",
        )
        return vectors[0] if vectors else None
    except Exception:
        return None


async def add_project_memory(
    settings: Settings,
    *,
    user_id: str,
    project_id: str,
    memory_text: str,
    source: str = "manual",
    confidence: float = 1.0,
) -> dict[str, Any]:
    if not configured(settings):
        raise RuntimeError("Supabase is not configured.")

    project = await get_project(settings, user_id=user_id, project_id=project_id)
    if not project:
        raise ValueError("Project not found.")

    cleaned = re.sub(r"\s+", " ", str(memory_text or "")).strip()
    if len(cleaned) < 3:
        raise ValueError("Project memory must contain at least 3 characters.")
    if len(cleaned) > 1200:
        raise ValueError("Project memory must be 1200 characters or fewer.")
    if personal._contains_private_data(cleaned):
        raise ValueError(
            "Passwords, API keys, OTPs, phone numbers and other sensitive data "
            "cannot be saved as project memory."
        )

    normalized = normalize_project_memory(cleaned)
    existing = await list_project_memories(
        settings, user_id=user_id, project_id=project_id, limit=200
    )
    for row in existing:
        old = str(row.get("normalized_text") or "").strip().casefold()
        if not old:
            old = normalize_project_memory(str(row.get("memory_text") or ""))
        if old == normalized:
            return {**row, "deduplicated": True}

    payload: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "project_id": project_id,
        "memory_text": cleaned,
        "normalized_text": normalized,
        "source": str(source or "manual")[:30],
        "confidence": max(0.0, min(float(confidence), 1.0)),
    }
    embedding = await _embed(cleaned, settings)
    if embedding is not None:
        payload["embedding"] = embedding

    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.post(
            f"{_base(settings)}/rest/v1/project_memories",
            headers=_headers(settings, representation=True),
            json=payload,
        )
    if response.status_code == 409:
        rows = await list_project_memories(
            settings, user_id=user_id, project_id=project_id, limit=200
        )
        for row in rows:
            if normalize_project_memory(str(row.get("memory_text") or "")) == normalized:
                return {**row, "deduplicated": True}
    response.raise_for_status()
    rows = response.json()
    return rows[0] if isinstance(rows, list) and rows else payload


async def delete_project_memory(
    settings: Settings,
    *,
    user_id: str,
    project_id: str,
    memory_id: str,
) -> bool:
    if not configured(settings):
        return False
    url = (
        f"{_base(settings)}/rest/v1/project_memories"
        f"?id=eq.{quote(memory_id)}"
        f"&project_id=eq.{quote(project_id)}"
        f"&user_id=eq.{quote(user_id)}"
    )
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.delete(url, headers=_headers(settings))
    return response.is_success


async def search_project_memories(
    settings: Settings,
    *,
    user_id: str,
    project_id: str,
    query: str,
    match_count: int = 8,
) -> list[dict[str, Any]]:
    safe_count = max(1, min(int(match_count), 12))
    clean_query = str(query or "").strip()

    if clean_query and settings.google_gemini_api:
        try:
            vector = await rag.embed_query(clean_query, settings)
            payload = {
                "p_user_id": user_id,
                "p_project_id": project_id,
                "p_query_embedding": vector,
                "p_match_count": safe_count,
                "p_min_similarity": 0.28,
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{_base(settings)}/rest/v1/rpc/match_project_memories",
                    headers=_headers(settings),
                    json=payload,
                )
            if response.is_success:
                rows = response.json()
                if isinstance(rows, list) and rows:
                    return rows
        except Exception:
            pass

    rows = await list_project_memories(
        settings, user_id=user_id, project_id=project_id, limit=100
    )
    if not clean_query:
        return rows[:safe_count]

    ranked: list[tuple[dict[str, Any], float]] = []
    for row in rows:
        score = _lexical_score(clean_query, str(row.get("memory_text") or ""))
        if score > 0:
            ranked.append(({**row, "similarity": score}, score))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return [item[0] for item in ranked[:safe_count]]


async def project_context_v8(
    settings: Settings,
    *,
    user_id: str,
    project_id: str,
    query: str,
) -> tuple[str, list[dict[str, Any]]]:
    project = await get_project(settings, user_id=user_id, project_id=project_id)
    if not project or project.get("archived"):
        return "", []

    memories = await search_project_memories(
        settings,
        user_id=user_id,
        project_id=project_id,
        query=query,
        match_count=8,
    )

    lines = [
        "ACTIVE PROJECT / WORKSPACE CONTEXT:",
        f"Project: {str(project.get('name') or '').strip()}",
        "Treat the following project instructions and memories as private user-provided context. "
        "Use them only when relevant and never reveal database/internal implementation details.",
    ]
    description = str(project.get("description") or "").strip()
    instructions = str(project.get("instructions") or "").strip()
    if description:
        lines.append(f"Project description: {description}")
    if instructions:
        lines.append(f"Project instructions: {instructions}")
    for index, row in enumerate(memories, 1):
        lines.append(f"[PROJECT MEMORY {index}] {str(row.get('memory_text') or '').strip()}")
    return "\n".join(lines), memories
