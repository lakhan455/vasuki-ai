from __future__ import annotations

from typing import Any

from app.services.router_v7 import RoutingDecision, base_candidates, configured_provider
from app.v17.provider_recovery import CODE_PROVIDER_ORDER


def zai_glm_health(settings: Any) -> dict[str, Any]:
    decision = RoutingDecision(
        task_type="code",
        difficulty="complex",
        tier="strong",
        language="en",
        needs_web=False,
    )
    code_order = base_candidates(decision, "auto")
    return {
        "ok": True,
        "version": "v44",
        "name": "Vasuki Z.AI GLM Coding Provider",
        "zai_glm": {
            "configured": configured_provider("zai_glm", settings),
            "model": str(getattr(settings, "zai_model", "") or ""),
            "base_url": str(getattr(settings, "zai_coding_base_url", "") or ""),
            "coding_priority": code_order.index("zai_glm") + 1
            if "zai_glm" in code_order
            else None,
            "endpoint_family": "openai-compatible-chat-completions",
            "coding_plan_endpoint": True,
        },
        "coding_auto_order": code_order,
        "autonomous_builder_order": list(CODE_PROVIDER_ORDER),
        "v43_instant_intent_preserved": True,
        "v42_dual_provider_preserved": True,
        "api_key_exposed_to_frontend": False,
        "db_migration_required": False,
        "new_python_dependency_required": False,
    }
