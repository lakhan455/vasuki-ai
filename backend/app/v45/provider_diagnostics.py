from __future__ import annotations


def provider_diagnostics_health() -> dict:
    return {
        "ok": True,
        "version": "v45",
        "name": "Vasuki Provider Diagnostics + Coding Stream Router",
        "features": [
            "normal-coding-stream-uses-opencode-zen",
            "normal-coding-stream-uses-zai-glm",
            "provider-model-diagnostics",
            "first-token-latency",
            "total-response-latency",
            "frontend-provider-badge",
        ],
        "coding_priority": ["opencode_zen", "zai_glm"],
        "extra_provider_call_required": False,
        "provider_racing_enabled": False,
        "v44_zai_glm_preserved": True,
        "v43_instant_intent_preserved": True,
        "db_migration_required": False,
        "new_api_key_required": False,
        "new_python_dependency_required": False,
    }
