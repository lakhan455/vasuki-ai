from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings


_PRIVATE_PATTERNS = (
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"(?<!\d)(?:\+?91[-\s]?)?[6-9]\d{9}(?!\d)"),
    re.compile(
        r"\b(password|passwd|api[_ -]?key|secret|access[_ -]?token|"
        r"refresh[_ -]?token|otp|aadhaar|pan card|cvv)\b",
        re.I,
    ),
)

_MEMORY_PREFIXES = (
    r"remember(?:\s+that)?\s+",
    r"please\s+remember(?:\s+that)?\s+",
    r"yaad\s+rakho(?:\s+ki)?\s+",
    r"yad\s+rakho(?:\s+ki)?\s+",
    r"याद\s+रखो(?:\s+कि)?\s+",
    r"meri\s+preference\s+(?:hai|he)\s+",
    r"my\s+preference\s+is\s+",
)


def _server_key(settings: Settings) -> str:
    return (
        settings.supabase_secret_key
        or settings.supabase_service_role_key
        or ""
    )


def _headers(
    settings: Settings,
    *,
    representation: bool = False,
    user_jwt: str | None = None,
) -> dict[str, str]:
    key = _server_key(settings)
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
    }
    if user_jwt:
        headers["Authorization"] = f"Bearer {user_jwt}"
    elif key and not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    if representation:
        headers["Prefer"] = "return=representation"
    return headers


def _base_url(settings: Settings) -> str:
    return (settings.supabase_url or "").rstrip("/")


def _configured(settings: Settings) -> bool:
    return bool(_base_url(settings) and _server_key(settings))


def _contains_private_data(value: str) -> bool:
    return any(pattern.search(value) for pattern in _PRIVATE_PATTERNS)


def clean_memory_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" \t\r\n.,;:-")
    if len(value) > 600:
        value = value[:600].rstrip()
    return value


_MEMORY_FOLLOWUP_BOUNDARY = re.compile(
    r"(?is)(?:"
    r"(?:\r?\n)+[ \t]*"
    r"|(?<=[.!?;])[ \t]+"
    r"|[ \t]+(?=now\s+(?:tell|answer|explain|analy[sz]e|show|give)\b)"
    r"|[ \t]+(?=ab\s+(?:batao|bata|samjhao|answer|tell)\b)"
    r")"
    r"(?=(?:"
    r"now\b|then\b|next\b|also\b|and\s+now\b|"
    r"please\s+(?:tell|answer)\b|tell\s+me\b|answer\b|"
    r"ab\b|aur\s+ab\b|अब\b|फिर\b|\d+[.)]\s+"
    r"))"
)


def _split_memory_and_followup(value: str) -> tuple[str, str]:
    raw = str(value or "").strip()
    if not raw:
        return "", ""

    match = _MEMORY_FOLLOWUP_BOUNDARY.search(raw)
    if not match:
        return clean_memory_text(raw), ""

    memory_text = clean_memory_text(raw[: match.start()])
    followup = raw[match.end() :].strip()
    return memory_text, followup


def extract_explicit_memory_command(query: str) -> tuple[str | None, str]:
    raw = str(query or "").strip()
    if not raw:
        return None, ""

    for prefix in _MEMORY_PREFIXES:
        match = re.match(prefix, raw, flags=re.I)
        if not match:
            continue

        candidate, followup = _split_memory_and_followup(raw[match.end() :])
        if (
            3 <= len(candidate) <= 600
            and not _contains_private_data(candidate)
        ):
            return candidate, followup
        return None, followup

    cleaned = clean_memory_text(raw)
    if re.search(
        r"\bmujhe\s+.+\s+(?:bolo|bulana|bulaya\s+karo)\b",
        cleaned,
        flags=re.I,
    ):
        if not _contains_private_data(cleaned):
            return cleaned, ""

    return None, ""


def explicit_memory_category(memory_text: str) -> str:
    low = clean_memory_text(memory_text).casefold()
    if re.search(
        r"\b(?:my goal is|my objective is|"
        r"mera goal (?:hai|he))\b",
        low,
    ):
        return "living_goal"
    if low.startswith(
        ("experience lesson:", "lesson:", "learned:")
    ):
        return "living_experience"
    return "preference"


def extract_explicit_memory(query: str) -> str | None:
    memory, _followup = extract_explicit_memory_command(query)
    return memory



async def get_memory_enabled(
    user_id: str,
    settings: Settings,
    *,
    user_jwt: str | None = None,
) -> bool:
    if not _configured(settings):
        return False

    url = (
        f"{_base_url(settings)}/rest/v1/user_memory_settings"
        f"?user_id=eq.{quote(user_id)}&select=enabled&limit=1"
    )
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            response = await client.get(url, headers=_headers(settings, user_jwt=user_jwt))
        if response.is_error:
            return True
        rows = response.json()
        if isinstance(rows, list) and rows:
            return bool(rows[0].get("enabled", True))
    except Exception:
        return True
    return True


async def set_memory_enabled(
    user_id: str,
    enabled: bool,
    settings: Settings,
    *,
    user_jwt: str | None = None,
) -> bool:
    if not _configured(settings):
        raise RuntimeError("Supabase server credentials are not configured.")

    url = (
        f"{_base_url(settings)}/rest/v1/user_memory_settings"
        "?on_conflict=user_id"
    )
    headers = {
        **_headers(settings),
        "Prefer": "resolution=merge-duplicates,return=representation",
    }
    payload = {"user_id": user_id, "enabled": enabled}

    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return enabled


async def list_user_memories(
    user_id: str,
    settings: Settings,
    *,
    limit: int = 50,
    user_jwt: str | None = None,
) -> list[dict[str, Any]]:
    if not _configured(settings):
        return []

    safe_limit = max(1, min(limit, 100))
    url = (
        f"{_base_url(settings)}/rest/v1/user_memories"
        f"?user_id=eq.{quote(user_id)}"
        "&select=id,memory_text,category,created_at,updated_at"
        "&order=updated_at.desc"
        f"&limit={safe_limit}"
    )

    try:
        async with httpx.AsyncClient(timeout=7.0) as client:
            response = await client.get(url, headers=_headers(settings, user_jwt=user_jwt))
        response.raise_for_status()
        rows = response.json()
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


async def create_user_memory(
    user_id: str,
    memory_text: str,
    settings: Settings,
    *,
    category: str = "preference",
    user_jwt: str | None = None,
) -> dict[str, Any]:
    if not _configured(settings):
        raise RuntimeError("Supabase server credentials are not configured.")

    cleaned = clean_memory_text(memory_text)
    if len(cleaned) < 3:
        raise ValueError("Memory must contain at least 3 characters.")
    if _contains_private_data(cleaned):
        raise ValueError(
            "Passwords, API keys, OTPs, phone numbers and other sensitive "
            "information cannot be saved as memory."
        )

    url = f"{_base_url(settings)}/rest/v1/user_memories"
    payload = {
        "user_id": user_id,
        "memory_text": cleaned,
        "category": clean_memory_text(category)[:40] or "preference",
    }

    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.post(
            url,
            headers=_headers(
                settings,
                representation=True,
                user_jwt=user_jwt,
            ),
            json=payload,
        )

    if response.status_code == 409:
        rows = await list_user_memories(
            user_id,
            settings,
            user_jwt=user_jwt,
        )
        for row in rows:
            if str(row.get("memory_text") or "").casefold() == cleaned.casefold():
                return row
        raise ValueError("This memory is already saved.")

    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list) or not rows:
        return {"memory_text": cleaned, "category": category}
    return rows[0]


async def delete_user_memory(
    user_id: str,
    memory_id: str,
    settings: Settings,
    *,
    user_jwt: str | None = None,
) -> None:
    if not _configured(settings):
        raise RuntimeError("Supabase server credentials are not configured.")

    url = (
        f"{_base_url(settings)}/rest/v1/user_memories"
        f"?id=eq.{quote(memory_id)}&user_id=eq.{quote(user_id)}"
    )
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.delete(url, headers=_headers(settings, user_jwt=user_jwt))
    response.raise_for_status()


async def personal_memory_context(
    user_id: str,
    settings: Settings,
    *,
    user_jwt: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    enabled = await get_memory_enabled(
        user_id,
        settings,
        user_jwt=user_jwt,
    )
    if not enabled:
        return "", []

    rows = await list_user_memories(
        user_id,
        settings,
        limit=30,
        user_jwt=user_jwt,
    )
    if not rows:
        return "", []

    lines = [
        "PRIVATE USER MEMORY:",
        "Use these only to personalize this user's answer. "
        "Never reveal that these came from a database unless asked.",
    ]
    for index, row in enumerate(rows, 1):
        lines.append(
            f"[USER MEMORY {index}] "
            f"{str(row.get('memory_text') or '').strip()}"
        )

    return "\n".join(lines), rows
