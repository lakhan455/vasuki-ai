from __future__ import annotations
from typing import Any
from app.services.omniroute_gateway_v10 import configured as omniroute_configured
from app.services.omniroute_knowledge_v10 import corpus_info

PROVIDER_FIELDS = {
    "groq": "groq_api_key", "cerebras": "cerebras_api_key", "sambanova": "sambanova_api_key",
    "gemini": "google_gemini_api", "openrouter": "openrouter_api", "mistral": "mistral_ai_api",
}
def _text(settings, name: str) -> str:
    return str(getattr(settings, name, "") or "").strip()

def registry(settings) -> dict[str, Any]:
    native = {name: bool(_text(settings, field)) for name, field in PROVIDER_FIELDS.items()}
    knowledge = corpus_info()
    omni_connected = omniroute_configured(settings)
    video_ready = bool(_text(settings, "v11_video_api_base_url") and _text(settings, "v11_video_api_key"))
    github_ready = bool(_text(settings, "v11_github_token"))
    tts_server = bool(_text(settings, "v11_tts_api_base_url") and _text(settings, "v11_tts_api_key"))
    stt_server = bool(_text(settings, "v11_stt_api_base_url") and _text(settings, "v11_stt_api_key"))
    return {
        "version": "v11",
        "quality": {"eval_engine": True, "fixed_eval_cases": 400, "automatic_answer_judge": True, "citation_fact_checker": True, "provider_quality_learning": True},
        "research": {"planner_v3": True, "parallel_search": True, "conflict_resolution": True, "research_kb": True},
        "coding": {"agent_v2": True, "test_fix_loop": True, "browser_js_sandbox": True, "browser_python_pyodide_sandbox": True, "server_untrusted_execution": False, "github_integration": github_ready, "project_knowledge_graph": True},
        "memory": {"conflict_resolver_v3": True, "temporal_memory": True, "supersedes": True},
        "media": {"image_consistency": True, "reference_controls": True, "mask_brush_workflow": True, "video_generation": video_ready, "audio_tts_browser": True, "audio_tts_server": tts_server, "speech_recognition_browser": True, "speech_to_speech": True, "server_stt": stt_server, "multimodal_request_api": True},
        "agents": {"tool_framework": True, "permission_system": True, "scheduled_tasks": True},
        "operations": {"slo_dashboard": True, "canary_release_policy": True, "automatic_rollback_hook": bool(_text(settings, "v11_rollback_webhook_url")), "db_performance": True, "abuse_protection": True, "privacy_center": True, "retention_policies": True, "accessibility_audit": True, "i18n_locales": ["en","hi","es","fr","de","ja"], "pwa_share_target": True},
        "omniroute": {
            "embedded_knowledge": "healthy" if knowledge.get("available") else "offline",
            "embedded_chunks": int(knowledge.get("chunks") or 0),
            "native_providers": native,
            "native_provider_count": sum(1 for value in native.values() if value),
            "native_provider_total": len(native),
            "sidecar": "connected" if omni_connected else "offline",
            "mcp": "enabled" if omni_connected and bool(getattr(settings, "v11_mcp_enabled", False)) else "disabled",
            "a2a": "enabled" if omni_connected and bool(getattr(settings, "v11_a2a_enabled", False)) else "disabled",
        },
        "external_dependencies": {
            "video": "configured" if video_ready else "needs V11_VIDEO_API_*",
            "github": "configured" if github_ready else "needs V11_GITHUB_TOKEN",
            "server_tts": "configured" if tts_server else "optional",
            "server_stt": "configured" if stt_server else "optional",
            "rollback": "configured" if _text(settings, "v11_rollback_webhook_url") else "optional webhook required for infra rollback",
        },
    }
