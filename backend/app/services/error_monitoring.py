from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.config import Settings
from app.services.chat_v4 import safe_error


_LAST_ALERT_AT = 0.0
_ALERT_LOCK = asyncio.Lock()


def _server_key(settings: Settings) -> str:
    return (
        settings.supabase_secret_key
        or settings.supabase_service_role_key
        or ""
    )


def _headers(settings: Settings) -> dict[str, str]:
    key = _server_key(settings)
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    if key and not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


async def record_error_event(
    settings: Settings,
    *,
    request_id: str,
    event_type: str,
    error: BaseException | str,
    provider: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist a sanitized error and optionally send a webhook alert."""

    clean_message = safe_error(
        error if isinstance(error, BaseException) else RuntimeError(str(error))
    )
    safe_metadata = {
        str(key)[:80]: str(value)[:300]
        for key, value in (metadata or {}).items()
    }

    tasks = []

    key = _server_key(settings)
    if settings.supabase_url and key:
        url = (
            f"{str(settings.supabase_url).rstrip('/')}"
            "/rest/v1/system_error_events"
        )
        payload = {
            "request_id": request_id[:80],
            "event_type": event_type[:80],
            "provider": provider[:80] or None,
            "error_message": clean_message,
            "metadata": safe_metadata,
        }

        async def save_event() -> None:
            try:
                async with httpx.AsyncClient(timeout=6.0) as client:
                    await client.post(
                        url,
                        headers=_headers(settings),
                        json=payload,
                    )
            except Exception:
                pass

        tasks.append(save_event())

    webhook_url = str(
        getattr(settings, "error_alert_webhook_url", "") or ""
    ).strip()
    if webhook_url:
        async def send_alert() -> None:
            global _LAST_ALERT_AT

            min_interval = max(
                30,
                int(
                    getattr(
                        settings,
                        "error_alert_min_interval_seconds",
                        300,
                    )
                ),
            )
            now = time.monotonic()

            async with _ALERT_LOCK:
                if now - _LAST_ALERT_AT < min_interval:
                    return
                _LAST_ALERT_AT = now

            message = (
                "Vasuki AI error\n"
                f"Request ID: {request_id}\n"
                f"Type: {event_type}\n"
                f"Provider: {provider or 'unknown'}\n"
                f"Error: {clean_message}"
            )
            try:
                async with httpx.AsyncClient(timeout=6.0) as client:
                    await client.post(
                        webhook_url,
                        json={"content": message, "text": message},
                    )
            except Exception:
                pass

        tasks.append(send_alert())

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
