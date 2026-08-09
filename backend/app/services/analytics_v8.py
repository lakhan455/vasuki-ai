from __future__ import annotations

import base64
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings


def _server_key(settings: Settings) -> str:
    return settings.supabase_secret_key or settings.supabase_service_role_key or ""


def _headers(settings: Settings, *, representation: bool = False) -> dict[str, str]:
    key = _server_key(settings)
    headers = {"apikey": key, "Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if representation:
        headers["Prefer"] = "return=representation"
    return headers


def _base(settings: Settings) -> str:
    return (settings.supabase_url or "").rstrip("/")


def configured(settings: Settings) -> bool:
    return bool(_base(settings) and _server_key(settings))


def jwt_subject(authorization: str | None) -> str | None:
    value = str(authorization or "")
    if not value.lower().startswith("bearer "):
        return None
    token = value.split(" ", 1)[1].strip()
    parts = token.split(".")
    if len(parts) < 2:
        return None
    try:
        raw = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(raw.encode()).decode())
        sub = str(payload.get("sub") or "").strip()
        return sub or None
    except Exception:
        return None


async def log_usage(
    settings: Settings,
    *,
    feature: str,
    user_id: str | None = None,
    provider: str | None = None,
    status: str = "ok",
    latency_ms: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not configured(settings):
        return
    payload = {
        "user_id": user_id,
        "feature": str(feature or "unknown")[:60],
        "provider": str(provider or "")[:80] or None,
        "status": str(status or "ok")[:40],
        "latency_ms": float(latency_ms) if latency_ms is not None else None,
        "metadata": metadata or {},
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{_base(settings)}/rest/v1/usage_events",
                headers=_headers(settings),
                json=payload,
            )
    except Exception:
        return


async def analytics_snapshot(settings: Settings, *, days: int = 7) -> dict[str, Any]:
    if not configured(settings):
        return {"configured": False}

    safe_days = max(1, min(int(days), 90))
    since = (datetime.now(timezone.utc) - timedelta(days=safe_days)).isoformat()
    url = (
        f"{_base(settings)}/rest/v1/usage_events"
        f"?created_at=gte.{quote(since)}"
        "&select=user_id,feature,provider,status,latency_ms,metadata,created_at"
        "&order=created_at.desc&limit=5000"
    )
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.get(url, headers=_headers(settings))
    response.raise_for_status()
    rows = response.json() if isinstance(response.json(), list) else []

    features = Counter(str(x.get("feature") or "unknown") for x in rows)
    providers = Counter(str(x.get("provider") or "") for x in rows if x.get("provider"))
    statuses = Counter(str(x.get("status") or "unknown") for x in rows)
    users = {str(x.get("user_id")) for x in rows if x.get("user_id")}
    latencies = [float(x["latency_ms"]) for x in rows if x.get("latency_ms") is not None]
    errors = sum(1 for x in rows if str(x.get("status") or "").casefold() not in {"ok", "success", "200"})
    quota_429 = sum(
        1 for x in rows
        if str(x.get("status") or "") == "429"
        or "429" in json.dumps(x.get("metadata") or {})
    )
    return {
        "configured": True,
        "period_days": safe_days,
        "requests": len(rows),
        "active_users": len(users),
        "features": dict(features),
        "providers": dict(providers),
        "statuses": dict(statuses),
        "average_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "errors": errors,
        "quota_429": quota_429,
    }
