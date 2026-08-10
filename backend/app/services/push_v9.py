from __future__ import annotations

import asyncio
import hashlib
import json
import os
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.services.analytics_v8 import _base, _headers, configured

try:
    from pywebpush import WebPushException, webpush
except Exception:  # pragma: no cover
    WebPushException = Exception
    webpush = None


def push_config() -> dict[str, Any]:
    public_key = os.getenv("VAPID_PUBLIC_KEY", "").strip()
    private_key = os.getenv("VAPID_PRIVATE_KEY", "").strip()
    subject = os.getenv("VAPID_SUBJECT", "mailto:admin@vasukinfc.in").strip()
    return {
        "configured": bool(public_key and private_key and webpush is not None),
        "public_key": public_key,
        "subject": subject,
    }


def _endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()


async def subscribe_push(
    settings: Settings,
    *,
    user_id: str,
    subscription: dict[str, Any],
    user_agent: str = "",
) -> dict[str, Any]:
    if not configured(settings):
        raise RuntimeError("Supabase is not configured.")
    endpoint = str(subscription.get("endpoint") or "").strip()
    keys = subscription.get("keys")
    if not endpoint.startswith("https://") or not isinstance(keys, dict):
        raise ValueError("Invalid browser push subscription.")
    if not str(keys.get("p256dh") or "") or not str(keys.get("auth") or ""):
        raise ValueError("Push subscription keys are missing.")
    payload = {
        "user_id": user_id,
        "endpoint_hash": _endpoint_hash(endpoint),
        "endpoint": endpoint[:2000],
        "subscription": subscription,
        "user_agent": user_agent[:500],
    }
    headers = dict(_headers(settings, representation=True))
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{_base(settings)}/rest/v1/push_subscriptions_v9?on_conflict=user_id,endpoint_hash",
            headers=headers,
            json=payload,
        )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if isinstance(rows, list) and rows else payload


async def unsubscribe_push(
    settings: Settings,
    *,
    user_id: str,
    endpoint: str,
) -> bool:
    if not configured(settings) or not endpoint:
        return False
    url = (
        f"{_base(settings)}/rest/v1/push_subscriptions_v9"
        f"?user_id=eq.{quote(user_id)}"
        f"&endpoint_hash=eq.{quote(_endpoint_hash(endpoint))}"
    )
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.delete(url, headers=_headers(settings))
    return response.is_success


async def _subscriptions(settings: Settings, user_id: str) -> list[dict[str, Any]]:
    if not configured(settings):
        return []
    url = (
        f"{_base(settings)}/rest/v1/push_subscriptions_v9"
        f"?user_id=eq.{quote(user_id)}"
        "&select=id,endpoint_hash,subscription&order=updated_at.desc&limit=20"
    )
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(url, headers=_headers(settings))
    if not response.is_success:
        return []
    rows = response.json()
    return rows if isinstance(rows, list) else []


async def send_push_notification(
    settings: Settings,
    *,
    user_id: str,
    title: str,
    body: str,
    action_url: str | None = None,
    kind: str = "info",
) -> dict[str, int]:
    config = push_config()
    if not config["configured"] or webpush is None:
        return {"sent": 0, "failed": 0}

    rows = await _subscriptions(settings, user_id)
    sent = 0
    failed = 0
    stale_hashes: list[str] = []
    data = json.dumps(
        {
            "title": str(title or "Vasuki AI")[:180],
            "body": str(body or "")[:1000],
            "url": str(action_url or "/")[:500],
            "kind": str(kind or "info")[:40],
        },
        ensure_ascii=False,
    )

    for row in rows:
        subscription = row.get("subscription")
        if not isinstance(subscription, dict):
            continue
        try:
            await asyncio.to_thread(
                webpush,
                subscription_info=subscription,
                data=data,
                vapid_private_key=os.getenv("VAPID_PRIVATE_KEY", "").strip(),
                vapid_claims={"sub": config["subject"]},
                ttl=300,
            )
            sent += 1
        except WebPushException as exc:
            failed += 1
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in {404, 410}:
                stale_hashes.append(str(row.get("endpoint_hash") or ""))
        except Exception:
            failed += 1

    if stale_hashes and configured(settings):
        async with httpx.AsyncClient(timeout=8.0) as client:
            for endpoint_hash in stale_hashes:
                await client.delete(
                    (
                        f"{_base(settings)}/rest/v1/push_subscriptions_v9"
                        f"?user_id=eq.{quote(user_id)}"
                        f"&endpoint_hash=eq.{quote(endpoint_hash)}"
                    ),
                    headers=_headers(settings),
                )
    return {"sent": sent, "failed": failed}
