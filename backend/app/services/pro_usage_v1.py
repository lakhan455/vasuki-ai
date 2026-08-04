from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.config import Settings


@dataclass(frozen=True, slots=True)
class ProImageQuota:
    allowed: bool
    image_count: int
    daily_limit: int
    daily_remaining: int
    persistent: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_FALLBACK: dict[tuple[str, str], int] = {}
_LOCK = asyncio.Lock()


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
    }
    if key and not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _today() -> str:
    return datetime.now(
        ZoneInfo("Asia/Kolkata"),
    ).date().isoformat()


async def _rpc(
    name: str,
    user_id: str,
    daily_limit: int,
    settings: Settings,
) -> ProImageQuota | None:
    base = (settings.supabase_url or "").rstrip("/")
    if not base or not _server_key(settings):
        return None

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                f"{base}/rest/v1/rpc/{name}",
                headers=_headers(settings),
                json={
                    "p_user_id": user_id,
                    "p_daily_limit": daily_limit,
                },
            )

        if response.is_error:
            return None

        payload = response.json()
        row = (
            payload[0]
            if isinstance(payload, list) and payload
            else payload
        )
        if not isinstance(row, dict):
            return None

        return ProImageQuota(
            allowed=bool(row.get("allowed", True)),
            image_count=int(row.get("image_count") or 0),
            daily_limit=daily_limit,
            daily_remaining=int(row.get("daily_remaining") or 0),
            persistent=True,
        )
    except Exception:
        return None


async def _local_change(
    user_id: str,
    daily_limit: int,
    delta: int,
) -> ProImageQuota:
    key = (user_id, _today())

    async with _LOCK:
        current = _FALLBACK.get(key, 0)

        if delta > 0 and current >= daily_limit:
            return ProImageQuota(
                allowed=False,
                image_count=current,
                daily_limit=daily_limit,
                daily_remaining=0,
                persistent=False,
            )

        current = max(0, min(daily_limit, current + delta))
        _FALLBACK[key] = current

    return ProImageQuota(
        allowed=True,
        image_count=current,
        daily_limit=daily_limit,
        daily_remaining=max(0, daily_limit - current),
        persistent=False,
    )


async def consume_pro_image_quota(
    user_id: str,
    settings: Settings,
) -> ProImageQuota:
    limit = max(
        1,
        int(getattr(settings, "pro_image_daily_limit", 100)),
    )
    result = await _rpc(
        "consume_pro_image_quota",
        user_id,
        limit,
        settings,
    )
    return result or await _local_change(
        user_id,
        limit,
        1,
    )


async def release_pro_image_quota(
    user_id: str,
    settings: Settings,
) -> ProImageQuota:
    limit = max(
        1,
        int(getattr(settings, "pro_image_daily_limit", 100)),
    )
    result = await _rpc(
        "release_pro_image_quota",
        user_id,
        limit,
        settings,
    )
    return result or await _local_change(
        user_id,
        limit,
        -1,
    )
