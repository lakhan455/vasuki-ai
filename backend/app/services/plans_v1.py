from __future__ import annotations

import hashlib
import hmac
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from app.auth import AuthUser
from app.config import Settings


@dataclass(frozen=True, slots=True)
class PlanStatus:
    plan: str
    is_owner: bool
    puter_access: bool
    pro_expires_at: str | None
    amount_paise: int
    plan_days: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _server_key(settings: Settings) -> str:
    return settings.supabase_secret_key or settings.supabase_service_role_key or ""


def _headers(settings: Settings, *, representation: bool = False, upsert: bool = False) -> dict[str, str]:
    key = _server_key(settings)
    headers = {"apikey": key, "Content-Type": "application/json"}
    if key and not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    prefer: list[str] = []
    if upsert:
        prefer.append("resolution=merge-duplicates")
    if representation:
        prefer.append("return=representation")
    if prefer:
        headers["Prefer"] = ",".join(prefer)
    return headers


def _base(settings: Settings) -> str:
    return (settings.supabase_url or "").rstrip("/")


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _owner_emails(settings: Settings) -> set[str]:
    return {x.strip().casefold() for x in settings.vasuki_owner_emails.split(",") if x.strip()}


def is_owner(user: AuthUser, settings: Settings) -> bool:
    return bool(user.email and user.email.strip().casefold() in _owner_emails(settings))


async def _plan_row(user_id: str, settings: Settings) -> dict[str, Any] | None:
    if not _base(settings) or not _server_key(settings):
        return None
    url = (
        f"{_base(settings)}/rest/v1/user_plans"
        f"?user_id=eq.{quote(user_id)}&select=plan,pro_expires_at,updated_at&limit=1"
    )
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(url, headers=_headers(settings))
        if response.is_error:
            return None
        rows = response.json()
        return rows[0] if isinstance(rows, list) and rows else None
    except Exception:
        return None


async def get_plan_status(user: AuthUser, settings: Settings) -> PlanStatus:
    if is_owner(user, settings):
        return PlanStatus(
            plan="owner",
            is_owner=True,
            puter_access=True,
            pro_expires_at=None,
            amount_paise=settings.razorpay_plan_amount_paise,
            plan_days=settings.razorpay_plan_days,
        )

    row = await _plan_row(user.id, settings)
    expires = _parse_dt((row or {}).get("pro_expires_at"))
    active = bool(
        row
        and str(row.get("plan") or "").casefold() == "pro"
        and expires
        and expires > datetime.now(timezone.utc)
    )
    return PlanStatus(
        plan="pro" if active else "free",
        is_owner=False,
        puter_access=active,
        pro_expires_at=expires.isoformat() if active and expires else None,
        amount_paise=settings.razorpay_plan_amount_paise,
        plan_days=settings.razorpay_plan_days,
    )


async def require_puter_access(user: AuthUser, settings: Settings) -> PlanStatus:
    status = await get_plan_status(user, settings)
    if not status.puter_access:
        raise HTTPException(status_code=403, detail="Puter Pro is locked. Activate the ₹99 30-day plan to continue.")
    return status


async def _upsert(settings: Settings, table: str, payload: dict[str, Any], conflict: str) -> None:
    if not _base(settings) or not _server_key(settings):
        raise HTTPException(status_code=503, detail="Supabase billing storage is not configured.")
    url = f"{_base(settings)}/rest/v1/{table}?on_conflict={quote(conflict)}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            url,
            headers=_headers(settings, representation=True, upsert=True),
            json=payload,
        )
    response.raise_for_status()


async def _patch(settings: Settings, table: str, query: str, payload: dict[str, Any]) -> None:
    url = f"{_base(settings)}/rest/v1/{table}?{query}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.patch(url, headers=_headers(settings), json=payload)
    response.raise_for_status()


async def activate_pro(user_id: str, settings: Settings, *, payment_id: str, order_id: str) -> str:
    row = await _plan_row(user_id, settings)
    existing = _parse_dt((row or {}).get("pro_expires_at"))
    now = datetime.now(timezone.utc)
    start = existing if existing and existing > now else now
    expires = start + timedelta(days=settings.razorpay_plan_days)
    await _upsert(
        settings,
        "user_plans",
        {
            "user_id": user_id,
            "plan": "pro",
            "pro_expires_at": expires.isoformat(),
            "source": "razorpay",
            "last_payment_id": payment_id,
            "last_order_id": order_id,
            "updated_at": now.isoformat(),
        },
        "user_id",
    )
    return expires.isoformat()


async def create_razorpay_order(user: AuthUser, settings: Settings) -> dict[str, Any]:
    if is_owner(user, settings):
        raise HTTPException(status_code=400, detail="The owner account does not require payment.")
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(status_code=503, detail="Razorpay keys are not configured yet.")

    amount = int(settings.razorpay_plan_amount_paise)
    payload = {
        "amount": amount,
        "currency": "INR",
        "receipt": f"vasuki_{user.id.replace('-', '')[:18]}",
        "notes": {"user_id": user.id, "email": user.email or "", "plan": "vasuki_pro_30_days"},
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            "https://api.razorpay.com/v1/orders",
            auth=httpx.BasicAuth(settings.razorpay_key_id, settings.razorpay_key_secret),
            json=payload,
        )
    if response.is_error:
        raise HTTPException(status_code=502, detail="The Razorpay order could not be created.")
    order = response.json()
    order_id = str(order.get("id") or "")
    if not order_id:
        raise HTTPException(status_code=502, detail="Invalid Razorpay order.")

    await _upsert(
        settings,
        "payment_orders",
        {
            "order_id": order_id,
            "user_id": user.id,
            "amount_paise": amount,
            "currency": "INR",
            "status": "created",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        "order_id",
    )
    return {
        "key_id": settings.razorpay_key_id,
        "order_id": order_id,
        "amount": amount,
        "currency": "INR",
        "name": "Vasuki AI",
        "description": f"Vasuki Pro — {settings.razorpay_plan_days} Days",
    }


async def _order_user(order_id: str, settings: Settings) -> str | None:
    url = f"{_base(settings)}/rest/v1/payment_orders?order_id=eq.{quote(order_id)}&select=user_id&limit=1"
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(url, headers=_headers(settings))
    if response.is_error:
        return None
    rows = response.json()
    return str(rows[0].get("user_id") or "") if isinstance(rows, list) and rows else None


async def verify_razorpay_payment(
    user: AuthUser,
    settings: Settings,
    *,
    order_id: str,
    payment_id: str,
    signature: str,
) -> dict[str, Any]:
    secret = settings.razorpay_key_secret or ""
    expected = hmac.new(
        secret.encode(),
        f"{order_id}|{payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=400, detail="Invalid payment signature.")
    if await _order_user(order_id, settings) != user.id:
        raise HTTPException(status_code=403, detail="Payment order user mismatch.")

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"https://api.razorpay.com/v1/payments/{quote(payment_id)}",
            auth=httpx.BasicAuth(settings.razorpay_key_id or "", secret),
        )
    if response.is_error:
        raise HTTPException(status_code=502, detail="The payment status could not be verified.")
    payment = response.json()
    if str(payment.get("order_id") or "") != order_id:
        raise HTTPException(status_code=400, detail="Payment order mismatch.")
    if int(payment.get("amount") or 0) != settings.razorpay_plan_amount_paise:
        raise HTTPException(status_code=400, detail="Payment amount mismatch.")
    if str(payment.get("currency") or "") != "INR":
        raise HTTPException(status_code=400, detail="Payment currency mismatch.")
    if str(payment.get("status") or "") != "captured":
        raise HTTPException(status_code=409, detail="Wait for the payment to be captured, then refresh.")

    expires = await activate_pro(user.id, settings, payment_id=payment_id, order_id=order_id)
    await _patch(
        settings,
        "payment_orders",
        f"order_id=eq.{quote(order_id)}&user_id=eq.{quote(user.id)}",
        {
            "status": "paid",
            "payment_id": payment_id,
            "signature": signature,
            "paid_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"ok": True, "plan": "pro", "pro_expires_at": expires, "puter_access": True}


async def process_razorpay_webhook(raw_body: bytes, signature: str, settings: Settings) -> dict[str, Any]:
    secret = settings.razorpay_webhook_secret or ""
    if not secret:
        raise HTTPException(status_code=503, detail="Webhook secret not configured.")
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature or ""):
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    import json
    event = json.loads(raw_body.decode())
    event_name = str(event.get("event") or "")
    if event_name not in {"order.paid", "payment.captured"}:
        return {"ok": True, "ignored": event_name}

    payload = event.get("payload") or {}
    payment = ((payload.get("payment") or {}).get("entity") or {})
    order = ((payload.get("order") or {}).get("entity") or {})
    order_id = str(order.get("id") or payment.get("order_id") or "")
    payment_id = str(payment.get("id") or "")
    user_id = str((order.get("notes") or {}).get("user_id") or "")
    if not user_id and order_id:
        user_id = await _order_user(order_id, settings) or ""
    if not order_id or not payment_id or not user_id:
        return {"ok": True, "ignored": "missing identifiers"}

    expires = await activate_pro(user_id, settings, payment_id=payment_id, order_id=order_id)
    await _patch(
        settings,
        "payment_orders",
        f"order_id=eq.{quote(order_id)}",
        {"status": "paid", "payment_id": payment_id, "paid_at": datetime.now(timezone.utc).isoformat()},
    )
    return {"ok": True, "pro_expires_at": expires}
