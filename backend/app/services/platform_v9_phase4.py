from __future__ import annotations

import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.services.analytics_v8 import _base, _headers, configured


DEFAULT_PLAN_POLICY: dict[str, dict[str, Any]] = {
    "free": {
        "background_jobs_daily": 5,
        "active_background_jobs": 1,
        "image_variations_max": 2,
        "allowed_background_kinds": [
            "image.generate",
            "image.variations",
        ],
    },
    "pro": {
        "background_jobs_daily": 40,
        "active_background_jobs": 3,
        "image_variations_max": 4,
        "allowed_background_kinds": [
            "image.generate",
            "image.variations",
            "project.code.patch",
            "project.tests.generate",
            "project.debug",
        ],
    },
    "owner": {
        "background_jobs_daily": 500,
        "active_background_jobs": 12,
        "image_variations_max": 4,
        "allowed_background_kinds": [
            "image.generate",
            "image.variations",
            "project.code.patch",
            "project.tests.generate",
            "project.debug",
        ],
    },
}

DEFAULT_FLAGS: dict[str, dict[str, Any]] = {
    "background_jobs_v9": {
        "enabled": True,
        "rollout_percent": 100,
        "variants": {},
        "description": "Persistent background job queue.",
    },
    "notification_center_v9": {
        "enabled": True,
        "rollout_percent": 100,
        "variants": {},
        "description": "In-app notification center.",
    },
    "usage_dashboard_v9": {
        "enabled": True,
        "rollout_percent": 100,
        "variants": {},
        "description": "Per-user usage dashboard.",
    },
    "plan_policy_v3": {
        "enabled": True,
        "rollout_percent": 100,
        "variants": {},
        "description": "Plan-aware policy engine.",
    },
    "owner_cost_dashboard_v9": {
        "enabled": True,
        "rollout_percent": 100,
        "variants": {},
        "description": "Owner cost and quota observability.",
    },
    "operations_refresh_cadence": {
        "enabled": True,
        "rollout_percent": 100,
        "variants": {"control": 50, "fast": 50},
        "description": "A/B experiment for Operations Center refresh cadence.",
    },
}


def stable_bucket(user_id: str, key: str) -> int:
    digest = hashlib.sha256(f"{key}:{user_id}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def weighted_variant(user_id: str, experiment: str, variants: dict[str, Any]) -> str | None:
    cleaned: list[tuple[str, int]] = []
    for name, raw_weight in (variants or {}).items():
        try:
            weight = max(0, int(raw_weight))
        except Exception:
            continue
        if weight > 0:
            cleaned.append((str(name), weight))
    if not cleaned:
        return None
    total = sum(weight for _name, weight in cleaned)
    point = int(
        hashlib.sha256(f"variant:{experiment}:{user_id}".encode("utf-8")).hexdigest()[:8],
        16,
    ) % total
    cursor = 0
    for name, weight in cleaned:
        cursor += weight
        if point < cursor:
            return name
    return cleaned[-1][0]


def _json_env(name: str) -> dict[str, Any]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def plan_policy(plan: str) -> dict[str, Any]:
    key = str(plan or "free").strip().casefold()
    if key not in DEFAULT_PLAN_POLICY:
        key = "free"
    policy = {
        **DEFAULT_PLAN_POLICY[key],
        "allowed_background_kinds": list(DEFAULT_PLAN_POLICY[key]["allowed_background_kinds"]),
    }
    overrides = _json_env("VASUKI_PLAN_POLICY_JSON")
    plan_override = overrides.get(key)
    if isinstance(plan_override, dict):
        for field, value in plan_override.items():
            if field == "allowed_background_kinds" and isinstance(value, list):
                policy[field] = [str(item) for item in value if str(item).strip()]
            elif field in {
                "background_jobs_daily",
                "active_background_jobs",
                "image_variations_max",
            }:
                try:
                    policy[field] = max(0, int(value))
                except Exception:
                    pass
    return {"plan": key, **policy}


def evaluate_job_policy(
    *,
    plan: str,
    kind: str,
    payload: dict[str, Any],
    daily_count: int,
    active_count: int,
) -> tuple[bool, str, dict[str, Any]]:
    policy = plan_policy(plan)
    if kind not in set(policy["allowed_background_kinds"]):
        return False, f"{kind} is not available as a background job on the {policy['plan']} plan.", policy
    if int(daily_count) >= int(policy["background_jobs_daily"]):
        return False, "Daily background job limit reached.", policy
    if int(active_count) >= int(policy["active_background_jobs"]):
        return False, "Too many background jobs are already active.", policy
    if kind == "image.variations":
        try:
            count = int(payload.get("count") or 4)
        except Exception:
            count = 4
        if count > int(policy["image_variations_max"]):
            return (
                False,
                f"This plan allows up to {policy['image_variations_max']} image variations per background job.",
                policy,
            )
    return True, "", policy


async def _get_rows(settings: Settings, table: str, query: str, timeout: float = 10.0) -> list[dict[str, Any]]:
    if not configured(settings):
        return []
    url = f"{_base(settings)}/rest/v1/{table}?{query}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, headers=_headers(settings))
    response.raise_for_status()
    value = response.json()
    return value if isinstance(value, list) else []


async def load_feature_flags(settings: Settings) -> dict[str, dict[str, Any]]:
    flags = {key: dict(value) for key, value in DEFAULT_FLAGS.items()}
    env_flags = _json_env("VASUKI_FEATURE_FLAGS_V3_JSON")
    for key, value in env_flags.items():
        if not isinstance(value, dict):
            continue
        base = dict(flags.get(str(key), {
            "enabled": True,
            "rollout_percent": 100,
            "variants": {},
            "description": "",
        }))
        base.update(value)
        flags[str(key)] = base

    if configured(settings):
        try:
            rows = await _get_rows(
                settings,
                "feature_flags_v9",
                "select=key,enabled,rollout_percent,variants,description,updated_at&order=key.asc&limit=500",
            )
            for row in rows:
                key = str(row.get("key") or "").strip()
                if not key:
                    continue
                base = dict(flags.get(key, {}))
                base.update({
                    "enabled": bool(row.get("enabled", True)),
                    "rollout_percent": max(0, min(100, int(row.get("rollout_percent") or 0))),
                    "variants": row.get("variants") if isinstance(row.get("variants"), dict) else {},
                    "description": str(row.get("description") or ""),
                    "updated_at": row.get("updated_at"),
                    "source": "database",
                })
                flags[key] = base
        except Exception:
            pass

    for key, value in flags.items():
        value["enabled"] = bool(value.get("enabled", True))
        try:
            value["rollout_percent"] = max(0, min(100, int(value.get("rollout_percent", 100))))
        except Exception:
            value["rollout_percent"] = 100
        if not isinstance(value.get("variants"), dict):
            value["variants"] = {}
        value.setdefault("source", "default")
        value.setdefault("description", "")
    return flags


async def feature_assignments(settings: Settings, user_id: str) -> dict[str, dict[str, Any]]:
    flags = await load_feature_flags(settings)
    output: dict[str, dict[str, Any]] = {}
    for key, config in flags.items():
        bucket = stable_bucket(user_id, key)
        rollout = int(config.get("rollout_percent") or 0)
        enabled = bool(config.get("enabled")) and (rollout >= 100 or bucket < rollout)
        variant = weighted_variant(user_id, key, config.get("variants") or {}) if enabled else None
        output[key] = {
            "enabled": enabled,
            "rollout_percent": rollout,
            "bucket": bucket,
            "variant": variant,
            "description": config.get("description") or "",
            "source": config.get("source") or "default",
        }
    return output


async def upsert_feature_flag(
    settings: Settings,
    *,
    key: str,
    enabled: bool,
    rollout_percent: int,
    variants: dict[str, Any] | None,
    description: str,
) -> dict[str, Any]:
    if not configured(settings):
        raise RuntimeError("Supabase is not configured.")
    clean_key = str(key or "").strip()[:100]
    if not clean_key:
        raise ValueError("Feature flag key is required.")
    payload = {
        "key": clean_key,
        "enabled": bool(enabled),
        "rollout_percent": max(0, min(100, int(rollout_percent))),
        "variants": variants or {},
        "description": str(description or "")[:500],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    headers = dict(_headers(settings, representation=True))
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{_base(settings)}/rest/v1/feature_flags_v9?on_conflict=key",
            headers=headers,
            json=payload,
        )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if isinstance(rows, list) and rows else payload


async def log_experiment_event(
    settings: Settings,
    *,
    user_id: str,
    experiment: str,
    variant: str,
    event: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not configured(settings):
        return
    payload = {
        "user_id": user_id,
        "experiment": str(experiment or "")[:100],
        "variant": str(variant or "")[:100],
        "event": str(event or "exposure")[:40],
        "metadata": metadata or {},
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{_base(settings)}/rest/v1/experiment_events_v9",
                headers=_headers(settings),
                json=payload,
            )
    except Exception:
        return


async def create_notification(
    settings: Settings,
    *,
    user_id: str,
    title: str,
    body: str,
    kind: str = "info",
    action_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not configured(settings):
        return None
    payload = {
        "user_id": user_id,
        "title": str(title or "Vasuki AI")[:180],
        "body": str(body or "")[:1200],
        "kind": str(kind or "info")[:40],
        "action_url": str(action_url or "")[:500] or None,
        "metadata": metadata or {},
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                f"{_base(settings)}/rest/v1/notifications_v9",
                headers=_headers(settings, representation=True),
                json=payload,
            )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if isinstance(rows, list) and rows else payload
    except Exception:
        return None


async def list_notifications(
    settings: Settings,
    *,
    user_id: str,
    limit: int = 80,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 200))
    rows = await _get_rows(
        settings,
        "notifications_v9",
        (
            f"user_id=eq.{quote(user_id)}"
            "&select=id,title,body,kind,action_url,metadata,read_at,created_at"
            "&order=created_at.desc"
            f"&limit={safe_limit}"
        ),
    )
    return {
        "items": rows,
        "unread": sum(1 for row in rows if not row.get("read_at")),
    }


async def mark_notification_read(settings: Settings, *, user_id: str, notification_id: str) -> bool:
    if not configured(settings):
        return False
    query = f"id=eq.{quote(notification_id)}&user_id=eq.{quote(user_id)}"
    payload = {"read_at": datetime.now(timezone.utc).isoformat()}
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.patch(
            f"{_base(settings)}/rest/v1/notifications_v9?{query}",
            headers=_headers(settings),
            json=payload,
        )
    return response.is_success


async def mark_all_notifications_read(settings: Settings, *, user_id: str) -> bool:
    if not configured(settings):
        return False
    payload = {"read_at": datetime.now(timezone.utc).isoformat()}
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.patch(
            (
                f"{_base(settings)}/rest/v1/notifications_v9"
                f"?user_id=eq.{quote(user_id)}&read_at=is.null"
            ),
            headers=_headers(settings),
            json=payload,
        )
    return response.is_success


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if number < 0 or number != number:
        return None
    return number


def summarize_usage_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    features = Counter(str(row.get("feature") or "unknown") for row in rows)
    providers = Counter(str(row.get("provider") or "") for row in rows if row.get("provider"))
    statuses = Counter(str(row.get("status") or "unknown") for row in rows)
    latencies = [
        float(row["latency_ms"])
        for row in rows
        if row.get("latency_ms") is not None
    ]
    errors = sum(
        1
        for row in rows
        if str(row.get("status") or "").casefold() not in {"ok", "success", "200"}
    )
    quota_429 = sum(
        1
        for row in rows
        if str(row.get("status") or "") == "429"
        or "429" in json.dumps(row.get("metadata") or {}, default=str)
    )

    reported_cost = 0.0
    estimated_cost = 0.0
    reported_events = 0
    estimated_events = 0
    provider_cost: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"reported_cost_usd": 0.0, "estimated_cost_usd": 0.0, "events": 0}
    )
    for row in rows:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        provider = str(row.get("provider") or "unattributed")
        provider_cost[provider]["events"] = int(provider_cost[provider]["events"]) + 1
        exact = _safe_float(metadata.get("cost_usd"))
        estimate = _safe_float(metadata.get("estimated_cost_usd"))
        if exact is not None:
            reported_cost += exact
            reported_events += 1
            provider_cost[provider]["reported_cost_usd"] = float(provider_cost[provider]["reported_cost_usd"]) + exact
        elif estimate is not None:
            estimated_cost += estimate
            estimated_events += 1
            provider_cost[provider]["estimated_cost_usd"] = float(provider_cost[provider]["estimated_cost_usd"]) + estimate

    daily: dict[str, int] = Counter()
    for row in rows:
        created = str(row.get("created_at") or "")
        if len(created) >= 10:
            daily[created[:10]] += 1

    return {
        "requests": len(rows),
        "features": dict(features),
        "providers": dict(providers),
        "statuses": dict(statuses),
        "average_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "errors": errors,
        "quota_429": quota_429,
        "daily": [{"date": key, "requests": daily[key]} for key in sorted(daily)],
        "cost": {
            "reported_cost_usd": round(reported_cost, 6),
            "estimated_cost_usd": round(estimated_cost, 6),
            "reported_cost_events": reported_events,
            "estimated_cost_events": estimated_events,
            "unpriced_events": max(0, len(rows) - reported_events - estimated_events),
            "by_provider": {
                key: {
                    "reported_cost_usd": round(float(value["reported_cost_usd"]), 6),
                    "estimated_cost_usd": round(float(value["estimated_cost_usd"]), 6),
                    "events": int(value["events"]),
                }
                for key, value in provider_cost.items()
            },
            "note": (
                "Costs are shown only when a provider/runtime explicitly logs cost_usd "
                "or estimated_cost_usd. Vasuki AI does not invent prices for unpriced events."
            ),
        },
    }


async def user_usage_snapshot(
    settings: Settings,
    *,
    user_id: str,
    days: int = 30,
) -> dict[str, Any]:
    safe_days = max(1, min(int(days), 90))
    since = (datetime.now(timezone.utc) - timedelta(days=safe_days)).isoformat()
    rows = await _get_rows(
        settings,
        "usage_events",
        (
            f"user_id=eq.{quote(user_id)}"
            f"&created_at=gte.{quote(since)}"
            "&select=feature,provider,status,latency_ms,metadata,created_at"
            "&order=created_at.desc&limit=5000"
        ),
        timeout=12.0,
    )
    return {
        "period_days": safe_days,
        **summarize_usage_rows(rows),
    }


async def owner_platform_snapshot(
    settings: Settings,
    *,
    days: int = 30,
) -> dict[str, Any]:
    safe_days = max(1, min(int(days), 90))
    since = (datetime.now(timezone.utc) - timedelta(days=safe_days)).isoformat()
    usage_rows = await _get_rows(
        settings,
        "usage_events",
        (
            f"created_at=gte.{quote(since)}"
            "&select=user_id,feature,provider,status,latency_ms,metadata,created_at"
            "&order=created_at.desc&limit=10000"
        ),
        timeout=15.0,
    )
    usage = summarize_usage_rows(usage_rows)
    usage["active_users"] = len({str(row.get("user_id")) for row in usage_rows if row.get("user_id")})

    job_rows = await _get_rows(
        settings,
        "background_jobs_v9",
        (
            f"created_at=gte.{quote(since)}"
            "&select=status,kind,attempts,created_at,finished_at"
            "&order=created_at.desc&limit=5000"
        ),
        timeout=12.0,
    )
    experiment_rows = await _get_rows(
        settings,
        "experiment_events_v9",
        (
            f"created_at=gte.{quote(since)}"
            "&select=experiment,variant,event,created_at"
            "&order=created_at.desc&limit=5000"
        ),
        timeout=12.0,
    )
    experiments: dict[str, dict[str, dict[str, int]]] = {}
    for row in experiment_rows:
        experiment = str(row.get("experiment") or "unknown")
        variant = str(row.get("variant") or "unknown")
        event = str(row.get("event") or "exposure")
        experiments.setdefault(experiment, {}).setdefault(variant, {"exposure": 0, "conversion": 0})
        if event == "conversion":
            experiments[experiment][variant]["conversion"] += 1
        else:
            experiments[experiment][variant]["exposure"] += 1

    return {
        "period_days": safe_days,
        "usage": usage,
        "jobs": {
            "total": len(job_rows),
            "statuses": dict(Counter(str(row.get("status") or "unknown") for row in job_rows)),
            "kinds": dict(Counter(str(row.get("kind") or "unknown") for row in job_rows)),
        },
        "experiments": experiments,
        "feature_flags": await load_feature_flags(settings),
    }
