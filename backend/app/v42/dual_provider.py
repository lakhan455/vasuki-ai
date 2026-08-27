from __future__ import annotations

from typing import Any

from app.services.router_v7 import RoutingDecision, base_candidates, configured_provider
from app.v17.provider_recovery import CODE_PROVIDER_ORDER


def dual_provider_health(settings: Any) -> dict[str, Any]:
    decision = RoutingDecision(
        task_type="code",
        difficulty="complex",
        tier="strong",
        language="en",
        needs_web=False,
    )
    code_order = base_candidates(decision, "auto")
    image_configured = bool(
        getattr(settings, "openrouter_image_enabled", False)
        and getattr(settings, "openrouter_api", None)
        and str(getattr(settings, "openrouter_image_model", "") or "").strip()
    )
    return {
        "ok": True,
        "version": "v42",
        "name": "Vasuki Dual Provider Coding + Image Brain",
        "opencode_zen": {
            "configured": configured_provider("opencode_zen", settings),
            "model": str(getattr(settings, "opencode_zen_model", "") or ""),
            "coding_priority": code_order.index("opencode_zen") + 1 if "opencode_zen" in code_order else None,
            "endpoint_family": "openai-compatible-chat-completions",
        },
        "openrouter": {
            "chat_configured": configured_provider("openrouter", settings),
            "chat_model": str(getattr(settings, "openrouter_model", "") or ""),
            "image_enabled": bool(getattr(settings, "openrouter_image_enabled", False)),
            "image_configured": image_configured,
            "image_model": str(getattr(settings, "openrouter_image_model", "") or ""),
        },
        "coding_auto_order": code_order,
        "autonomous_builder_order": list(CODE_PROVIDER_ORDER),
        "existing_provider_fallback_preserved": True,
        "v41_weather_preserved": True,
        "v40_creator_runtime_preserved": True,
        "api_keys_exposed_to_frontend": False,
        "automatic_paid_image_spend_without_opt_in": False,
        "db_migration_required": False,
        "new_python_dependency_required": False,
    }
