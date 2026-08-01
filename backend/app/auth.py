from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass

import httpx
from fastapi import Header, HTTPException

from app.config import get_settings


@dataclass(frozen=True, slots=True)
class AuthUser:
    id: str
    email: str | None = None
    access_token: str = ""


_CACHE: dict[str, tuple[float, AuthUser]] = {}
_CACHE_LOCK = asyncio.Lock()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _server_key() -> str:
    settings = get_settings()
    return (
        settings.supabase_secret_key
        or settings.supabase_service_role_key
        or ""
    )


async def get_current_user(
    authorization: str | None = Header(default=None),
) -> AuthUser:
    settings = get_settings()

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Login required. Please sign in again.",
        )

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Invalid access token.")

    if not settings.supabase_url or not _server_key():
        raise HTTPException(
            status_code=503,
            detail="Backend authentication is not configured.",
        )

    cache_key = _token_hash(token)
    now = time.monotonic()

    async with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]

    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/user"
    headers = {
        "apikey": _server_key(),
        "Authorization": f"Bearer {token}",
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication service is temporarily unavailable.",
        ) from exc

    if response.status_code in {401, 403}:
        raise HTTPException(
            status_code=401,
            detail="Your login session expired. Please sign in again.",
        )

    if response.is_error:
        raise HTTPException(
            status_code=503,
            detail="Authentication verification failed.",
        )

    payload = response.json()
    user_id = str(payload.get("id") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user account.")

    user = AuthUser(
        id=user_id,
        email=(
            str(payload.get("email"))
            if payload.get("email")
            else None
        ),
        access_token=token,
    )

    async with _CACHE_LOCK:
        _CACHE[cache_key] = (now + 45.0, user)
        if len(_CACHE) > 5000:
            expired = [
                key for key, value in _CACHE.items() if value[0] <= now
            ]
            for key in expired[:2500]:
                _CACHE.pop(key, None)

    return user
