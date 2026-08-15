from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import Settings
from app.services.rate_limit import CHAT_QUOTA, QuotaExceeded, QuotaStatus


INDIA_TIMEZONE = timezone(timedelta(hours=5, minutes=30))


def _server_key(settings: Settings) -> str:
    return (
        settings.supabase_secret_key
        or settings.supabase_service_role_key
        or ""
    )


def _configured(settings: Settings) -> bool:
    return bool(settings.supabase_url and _server_key(settings))


def _headers(settings: Settings) -> dict[str, str]:
    key = _server_key(settings)
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
    }
    if key and not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _parse_rpc_payload(payload: Any) -> tuple[bool, int, int]:
    row: Any = payload
    if isinstance(payload, list):
        row = payload[0] if payload else {}
    if not isinstance(row, dict):
        raise ValueError("Invalid quota response")

    allowed = bool(row.get("allowed", False))
    message_count = max(0, int(row.get("message_count", 0)))
    daily_remaining = max(0, int(row.get("daily_remaining", 0)))
    return allowed, message_count, daily_remaining


def _seconds_until_india_midnight() -> int:
    now = datetime.now(INDIA_TIMEZONE)
    tomorrow = (
        now.replace(hour=0, minute=0, second=0, microsecond=0)
        + timedelta(days=1)
    )
    return max(1, int((tomorrow - now).total_seconds()))


async def check_chat_quota(
    user_id: str,
    settings: Settings,
    *,
    minute_limit: int,
    daily_limit: int,
) -> QuotaStatus:
    """Apply local throttling plus a persistent Supabase daily counter."""

    local_status = await CHAT_QUOTA.check(
        user_id,
        minute_limit=minute_limit,
        daily_limit=daily_limit,
    )

    # A zero/negative daily limit means unlimited chat.
    # Keep the per-minute abuse guard, but do not consume
    # the persistent Supabase daily counter.
    if int(daily_limit) <= 0:
        return local_status

    if not _configured(settings):
        return local_status

    base_url = str(settings.supabase_url or "").rstrip("/")
    url = f"{base_url}/rest/v1/rpc/consume_chat_quota"

    try:
        async with httpx.AsyncClient(timeout=7.0) as client:
            response = await client.post(
                url,
                headers=_headers(settings),
                json={
                    "p_user_id": user_id,
                    "p_daily_limit": max(1, int(daily_limit)),
                },
            )

        # Backward-compatible until the SQL migration is installed.
        if response.status_code in {404, 405}:
            return local_status

        response.raise_for_status()
        allowed, _message_count, daily_remaining = _parse_rpc_payload(
            response.json()
        )
    except QuotaExceeded:
        raise
    except Exception:
        return local_status

    if not allowed:
        raise QuotaExceeded(
            "Today's free AI message quota has been reached. Please try again tomorrow.",
            retry_after_seconds=_seconds_until_india_midnight(),
        )

    return QuotaStatus(
        minute_limit=local_status.minute_limit,
        minute_remaining=local_status.minute_remaining,
        daily_limit=max(1, int(daily_limit)),
        daily_remaining=daily_remaining,
    )
