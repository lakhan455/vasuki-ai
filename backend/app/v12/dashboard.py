from __future__ import annotations

from typing import Any

from app.v11.capabilities import registry as v11_capabilities
from app.v11.operations import slo_snapshot
from app.v12.provider import provider_snapshot_v12
from app.v12.sandbox import sandbox_status


def _configured(settings, *names: str) -> bool:
    return all(
        bool(str(getattr(settings, name, "") or "").strip())
        for name in names
    )


def reliability_snapshot_v12(settings) -> dict[str, Any]:
    v11 = v11_capabilities(settings)
    slo = slo_snapshot()
    sandbox = sandbox_status()

    github = bool(
        str(getattr(settings, "v11_github_token", "") or "").strip()
    )

    video = _configured(
        settings,
        "v11_video_api_base_url",
        "v11_video_api_key",
    )

    tts = _configured(
        settings,
        "v11_tts_api_base_url",
        "v11_tts_api_key",
    )

    stt = _configured(
        settings,
        "v11_stt_api_base_url",
        "v11_stt_api_key",
    )

    return {
        "ok": True,
        "version": "v12",
        "slo": slo,
        "providers": provider_snapshot_v12(settings),
        "sandbox": sandbox,
        "capabilities": {
            "eval_benchmark": "online",
            "provider_quality_learning": "online",
            "citation_verification": "online",
            "memory_conflict_resolver": "online",
            "safe_code_sandbox": (
                "online" if sandbox["available"] else "needs-docker"
            ),
            "automatic_test_fix_retest": (
                "online" if sandbox["available"] else "needs-docker"
            ),
            "github": "online" if github else "not-configured",
            "video": "online" if video else "not-configured",
            "tts": "online" if tts else "browser-or-not-configured",
            "stt": "online" if stt else "browser-or-not-configured",
            "reliability_dashboard": "online",
        },
        "v11": v11,
    }
