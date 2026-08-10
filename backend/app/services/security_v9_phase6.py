from __future__ import annotations

import hashlib
import os
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.services.analytics_v8 import _base, _headers, configured

_SECRET_FIELDS = {
    "GROQ_API_KEY": "groq_api_key",
    "SAMBANOVA_API_KEY": "sambanova_api_key",
    "CEREBRAS_API_KEY": "cerebras_api_key",
    "GOOGLE_GEMINI_API": "google_gemini_api",
    "OPENROUTER_API": "openrouter_api",
    "MISTRAL_AI_API": "mistral_ai_api",
    "TAVILY_API_KEY": "tavily_api_key",
    "EXA_API": "exa_api",
    "NEWS_API": "news_api",
    "DEEPAI_API": "deepai_api",
    "HUGGING_FACE_INFERENCE_API": "hugging_face_inference_api",
    "CLOUDFLARE_WORKERS_AI": "cloudflare_workers_ai",
    "OCR_SPACE_API": "ocr_space_api",
    "SUPABASE_SECRET_KEY": "supabase_secret_key",
    "SUPABASE_SERVICE_ROLE_KEY": "supabase_service_role_key",
    "RAZORPAY_KEY_SECRET": "razorpay_key_secret",
    "RAZORPAY_WEBHOOK_SECRET": "razorpay_webhook_secret",
}
_ENV_SECRET_FIELDS = ["VAPID_PRIVATE_KEY", "VAPID_PUBLIC_KEY"]
_SENSITIVE_META_KEYS = {
    "authorization", "cookie", "set-cookie", "access_token", "refresh_token",
    "password", "secret", "api_key", "apikey", "private_key", "signature",
}


def _fingerprint(value: str | None) -> str | None:
    clean = str(value or "").strip()
    if not clean:
        return None
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()[:16]


def _safe_metadata(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return "[truncated]"
    if isinstance(value, list):
        return [_safe_metadata(item, depth=depth + 1) for item in value[:50]]
    if not isinstance(value, dict):
        if isinstance(value, str) and len(value) > 1500:
            return value[:1500] + "…"
        return value
    output: dict[str, Any] = {}
    for key, item in list(value.items())[:80]:
        low = str(key).casefold()
        if low in _SENSITIVE_META_KEYS or any(token in low for token in ("password", "secret", "token", "private_key")):
            output[str(key)] = "[redacted]"
        else:
            output[str(key)] = _safe_metadata(item, depth=depth + 1)
    return output


def _hash_client(value: str | None) -> str | None:
    clean = str(value or "").strip()
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()[:20] if clean else None


async def audit_event(
    settings: Settings,
    *,
    actor_user_id: str | None,
    action: str,
    outcome: str = "success",
    target_type: str | None = None,
    target_id: str | None = None,
    request_id: str | None = None,
    ip_value: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not configured(settings):
        return
    payload = {
        "actor_user_id": actor_user_id,
        "action": str(action or "unknown")[:120],
        "outcome": str(outcome or "unknown")[:40],
        "target_type": str(target_type or "")[:80] or None,
        "target_id": str(target_id or "")[:220] or None,
        "request_id": str(request_id or "")[:120] or None,
        "ip_hash": _hash_client(ip_value),
        "user_agent_hash": _hash_client(user_agent),
        "metadata": _safe_metadata(metadata or {}),
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{_base(settings)}/rest/v1/audit_logs_v9",
                headers=_headers(settings),
                json=payload,
            )
    except Exception:
        return


async def list_audit_logs(settings: Settings, *, days: int = 7, limit: int = 200) -> list[dict[str, Any]]:
    if not configured(settings):
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 90)))).isoformat()
    url = (
        f"{_base(settings)}/rest/v1/audit_logs_v9"
        f"?created_at=gte.{quote(since)}"
        "&select=id,actor_user_id,action,outcome,target_type,target_id,request_id,metadata,created_at"
        "&order=created_at.desc"
        f"&limit={max(1, min(limit, 500))}"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=_headers(settings))
    if response.status_code in {400, 404}:
        return []
    response.raise_for_status()
    rows = response.json()
    return rows if isinstance(rows, list) else []


async def error_event(
    settings: Settings,
    *,
    request_id: str,
    event_type: str,
    message: str,
    provider: str | None = None,
    severity: str = "error",
    metadata: dict[str, Any] | None = None,
) -> None:
    if not configured(settings):
        return
    fingerprint = hashlib.sha256(
        f"{event_type}|{provider or ''}|{str(message)[:400]}".encode("utf-8")
    ).hexdigest()[:24]
    payload = {
        "request_id": str(request_id or uuid.uuid4())[:120],
        "event_type": str(event_type or "unknown")[:120],
        "provider": str(provider or "")[:120] or None,
        "error_message": str(message or "unknown error")[:3000],
        "severity": str(severity or "error")[:30],
        "fingerprint": fingerprint,
        "metadata": _safe_metadata(metadata or {}),
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{_base(settings)}/rest/v1/system_error_events",
                headers=_headers(settings),
                json=payload,
            )
    except Exception:
        return


async def error_dashboard(settings: Settings, *, days: int = 7) -> dict[str, Any]:
    if not configured(settings):
        return {"configured": False, "total": 0, "recent": []}
    since = (datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 90)))).isoformat()
    url = (
        f"{_base(settings)}/rest/v1/system_error_events"
        f"?created_at=gte.{quote(since)}"
        "&select=id,request_id,event_type,provider,error_message,severity,fingerprint,resolved_at,metadata,created_at"
        "&order=created_at.desc&limit=1000"
    )
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.get(url, headers=_headers(settings))
    if response.status_code in {400, 404}:
        return {"configured": True, "total": 0, "recent": []}
    response.raise_for_status()
    rows = response.json() if isinstance(response.json(), list) else []
    groups = Counter(str(row.get("fingerprint") or row.get("event_type") or "unknown") for row in rows)
    types = Counter(str(row.get("event_type") or "unknown") for row in rows)
    providers = Counter(str(row.get("provider") or "unknown") for row in rows)
    unresolved = sum(1 for row in rows if not row.get("resolved_at"))
    return {
        "configured": True,
        "period_days": max(1, min(days, 90)),
        "total": len(rows),
        "unresolved": unresolved,
        "by_type": dict(types.most_common(12)),
        "by_provider": dict(providers.most_common(12)),
        "top_fingerprints": [{"fingerprint": key, "count": count} for key, count in groups.most_common(12)],
        "recent": rows[:120],
    }


async def resolve_error(settings: Settings, *, error_id: int, owner_user_id: str) -> bool:
    if not configured(settings):
        return False
    url = f"{_base(settings)}/rest/v1/system_error_events?id=eq.{int(error_id)}"
    payload = {"resolved_at": datetime.now(timezone.utc).isoformat(), "resolved_by": owner_user_id}
    headers = dict(_headers(settings))
    headers["Prefer"] = "return=representation"
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.patch(url, headers=headers, json=payload)
    return response.is_success and bool(response.json() if response.content else [])


def secret_inventory(settings: Settings) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for env_name, field_name in _SECRET_FIELDS.items():
        value = getattr(settings, field_name, None)
        items.append({"name": env_name, "configured": bool(str(value or "").strip()), "fingerprint": _fingerprint(value), "source": "settings"})
    for env_name in _ENV_SECRET_FIELDS:
        value = os.getenv(env_name, "")
        items.append({"name": env_name, "configured": bool(value.strip()), "fingerprint": _fingerprint(value), "source": "environment"})
    return items


def security_audit(settings: Settings) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    origins = [item.strip() for item in str(settings.allowed_origins or "").split(",") if item.strip()]
    if settings.app_env.casefold() != "production":
        findings.append({"severity": "high", "check": "production_environment", "detail": "APP_ENV is not production."})
    if not origins or "*" in origins:
        findings.append({"severity": "critical", "check": "cors_origins", "detail": "ALLOWED_ORIGINS must be explicit and must not contain *."})
    if not (settings.supabase_secret_key or settings.supabase_service_role_key):
        findings.append({"severity": "critical", "check": "server_database_key", "detail": "No backend Supabase server credential is configured."})
    if not str(settings.vasuki_owner_emails or "").strip():
        findings.append({"severity": "high", "check": "owner_identity", "detail": "VASUKI_OWNER_EMAILS is empty."})
    if not os.getenv("VAPID_PRIVATE_KEY", "").strip():
        findings.append({"severity": "medium", "check": "push_private_key", "detail": "VAPID private key is not configured."})
    if not settings.error_alert_webhook_url:
        findings.append({"severity": "low", "check": "external_error_alerting", "detail": "ERROR_ALERT_WEBHOOK_URL is not configured; the internal error dashboard still works."})
    configured_provider_count = sum(1 for row in secret_inventory(settings) if row["configured"] and row["name"] not in {"SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "VAPID_PRIVATE_KEY", "VAPID_PUBLIC_KEY"})
    if configured_provider_count < 2:
        findings.append({"severity": "medium", "check": "provider_resilience", "detail": "Fewer than two provider/payment/search secrets are configured."})
    penalties = {"critical": 25, "high": 14, "medium": 7, "low": 2}
    score = max(0, 100 - sum(penalties.get(row["severity"], 0) for row in findings))
    return {
        "score": score,
        "grade": "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F",
        "findings": findings,
        "configured_secrets": sum(1 for row in secret_inventory(settings) if row["configured"]),
        "secret_inventory": secret_inventory(settings),
        "note": "Secret values are never returned; only SHA-256 fingerprints are exposed to the owner API.",
    }


def current_secret_fingerprint(settings: Settings, secret_name: str) -> str | None:
    wanted = secret_name.strip().upper()
    for row in secret_inventory(settings):
        if row["name"] == wanted:
            return row.get("fingerprint")
    return None


async def record_secret_rotation(settings: Settings, *, owner_user_id: str, secret_name: str, previous_fingerprint: str, note: str = "") -> dict[str, Any]:
    name = secret_name.strip().upper()
    current = current_secret_fingerprint(settings, name)
    if not current:
        raise ValueError("That secret is not configured in the running backend.")
    previous = previous_fingerprint.strip().casefold()
    if previous == current.casefold():
        raise ValueError("Current secret fingerprint is unchanged. Rotate the Render secret first, redeploy, then record the rotation.")
    payload = {"secret_name": name[:120], "previous_fingerprint": previous[:64] or None, "current_fingerprint": current, "rotated_by": owner_user_id, "note": str(note or "")[:1000]}
    headers = dict(_headers(settings))
    headers["Prefer"] = "return=representation"
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.post(f"{_base(settings)}/rest/v1/secret_rotation_events_v9", headers=headers, json=payload)
    response.raise_for_status()
    rows = response.json()
    return rows[0] if isinstance(rows, list) and rows else payload


async def latest_eval(settings: Settings) -> dict[str, Any] | None:
    if not configured(settings):
        return None
    url = f"{_base(settings)}/rest/v1/eval_runs_v9?select=id,version,questions,overall_score,average_latency_ms,category_scores,metadata,created_at&order=created_at.desc&limit=1"
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(url, headers=_headers(settings))
    if response.status_code in {400, 404}:
        return None
    response.raise_for_status()
    rows = response.json()
    return rows[0] if isinstance(rows, list) and rows else None


async def list_evals(settings: Settings, *, limit: int = 20) -> list[dict[str, Any]]:
    if not configured(settings):
        return []
    url = f"{_base(settings)}/rest/v1/eval_runs_v9?select=id,version,questions,overall_score,average_latency_ms,category_scores,metadata,created_at&order=created_at.desc&limit={max(1, min(limit, 100))}"
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(url, headers=_headers(settings))
    if response.status_code in {400, 404}:
        return []
    response.raise_for_status()
    rows = response.json()
    return rows if isinstance(rows, list) else []


async def record_eval(settings: Settings, *, owner_user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = {
        "version": str(payload.get("version") or "v9")[:80],
        "questions": max(0, int(payload.get("questions") or 0)),
        "overall_score": max(0.0, min(100.0, float(payload.get("overall") or payload.get("overall_score") or 0))),
        "average_latency_ms": max(0.0, float(payload.get("average_latency_ms") or 0)),
        "category_scores": payload.get("scores") if isinstance(payload.get("scores"), dict) else payload.get("category_scores") or {},
        "recorded_by": owner_user_id,
        "metadata": _safe_metadata(payload.get("metadata") or {"source": "eval_runner"}),
    }
    headers = dict(_headers(settings))
    headers["Prefer"] = "return=representation"
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.post(f"{_base(settings)}/rest/v1/eval_runs_v9", headers=headers, json=row)
    response.raise_for_status()
    rows = response.json()
    return rows[0] if isinstance(rows, list) and rows else row


async def release_health(settings: Settings) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.append({"name": "production_env", "ok": settings.app_env.casefold() == "production"})
    checks.append({"name": "supabase_server_credentials", "ok": bool(settings.supabase_url and (settings.supabase_secret_key or settings.supabase_service_role_key))})
    checks.append({"name": "cors_explicit", "ok": "*" not in [item.strip() for item in str(settings.allowed_origins or "").split(",")]})
    checks.append({"name": "owner_identity", "ok": bool(str(settings.vasuki_owner_emails or "").strip())})
    checks.append({"name": "browser_push_keys", "ok": bool(os.getenv("VAPID_PUBLIC_KEY", "").strip() and os.getenv("VAPID_PRIVATE_KEY", "").strip())})
    db_ok = False
    if configured(settings):
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                response = await client.get(f"{_base(settings)}/rest/v1/audit_logs_v9?select=id&limit=1", headers=_headers(settings))
            db_ok = response.is_success
        except Exception:
            db_ok = False
    checks.append({"name": "phase6_database", "ok": db_ok})
    audit = security_audit(settings)
    checks.append({"name": "security_score_80_plus", "ok": int(audit["score"]) >= 80, "value": audit["score"]})
    eval_row = await latest_eval(settings)
    checks.append({"name": "latest_eval_available", "ok": bool(eval_row), "optional": True, "value": eval_row.get("overall_score") if eval_row else None})
    required = [row for row in checks if not row.get("optional")]
    status = "healthy" if all(bool(row.get("ok")) for row in required) else "degraded"
    snapshot = {"status": status, "checks": checks, "security_score": audit["score"], "latest_eval": eval_row, "checked_at": datetime.now(timezone.utc).isoformat()}
    if configured(settings):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{_base(settings)}/rest/v1/release_health_v9",
                    headers=_headers(settings),
                    json={"status": status, "checks": checks, "security_score": audit["score"], "eval_score": eval_row.get("overall_score") if eval_row else None},
                )
        except Exception:
            pass
    return snapshot
