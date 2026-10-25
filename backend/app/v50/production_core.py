from __future__ import annotations

from typing import Any

from app.v47.reliability_router import reliability_snapshot, v47_health
from app.v49.live_knowledge import live_knowledge_status
from app.v50.provider_guard import configured_model_snapshot
from app.v50.telemetry import snapshot as degraded_snapshot


def health_snapshot(settings: Any) -> dict[str, Any]:
    live = live_knowledge_status(settings)
    return {
        "ok": True,
        "version": "v50",
        "name": "Vasuki Production Intelligence Core",
        "truth": {
            "generic_truth_guard_enabled": bool(
                getattr(settings, "v50_generic_truth_guard_enabled", True)
            ),
            "min_sources": int(getattr(settings, "v50_truth_min_sources", 2)),
            "min_domains": int(getattr(settings, "v50_truth_min_domains", 2)),
            "authoritative_cm_guard": bool(
                getattr(settings, "v49_1_authoritative_current_facts_enabled", True)
            ),
        },
        "providers": {
            "model_fallback_enabled": bool(
                getattr(settings, "v50_model_fallback_enabled", True)
            ),
            "models": configured_model_snapshot(settings),
            "reliability": v47_health(settings),
            "runtime": reliability_snapshot(),
        },
        "live_knowledge": {
            "enabled": live.get("enabled"),
            "search_ready": live.get("search_ready"),
            "storage_ready": live.get("storage_ready"),
            "runtime": live.get("runtime"),
            "durable_checkpoint": bool(
                getattr(settings, "v50_persist_runtime_state", True)
            ),
            "external_scheduler_endpoint_configured": bool(
                str(getattr(settings, "v50_cron_secret", "") or "").strip()
            ),
        },
        "degraded_mode": degraded_snapshot(limit=30),
        "architecture": {
            "policy_layer": "app.v50",
            "legacy_compatibility": "V11-V49 behavior retained behind V50 guards",
            "new_database_migration_required": False,
        },
    }
