from __future__ import annotations

import logging
import time
from typing import Any

from app.config import Settings
from app.services.chat import chat_vasuki_cloud
from app.v50.telemetry import record_degraded


_LOGGER = logging.getLogger("uvicorn.error")

_CANARY_PROMPT = "Reply only with: VASUKI CLOUD READY"
_CANARY_EXPECTED = "VASUKI CLOUD READY"


async def run_cloud_startup_probe(
    settings: Settings,
) -> dict[str, Any]:
    """Run a controlled Vasuki Cloud connectivity check.

    This function never exposes credentials or model output in logs.
    Failures are recorded but never crash application startup.
    """
    enabled = bool(
        getattr(
            settings,
            "vasuki_cloud_enabled",
            False,
        )
    )
    probe_enabled = bool(
        getattr(
            settings,
            "vasuki_cloud_startup_probe",
            False,
        )
    )

    if not enabled or not probe_enabled:
        return {
            "ran": False,
            "ok": False,
            "status": "disabled",
        }

    started = time.perf_counter()

    try:
        answer = await chat_vasuki_cloud(
            [
                {
                    "role": "user",
                    "content": _CANARY_PROMPT,
                }
            ],
            settings,
            "",
            require_current=False,
            as_of=None,
            temperature=0.0,
        )

        normalized = str(answer or "").strip().upper()

        if _CANARY_EXPECTED not in normalized:
            raise RuntimeError(
                "Vasuki Cloud canary returned an unexpected response"
            )

    except Exception as exc:
        latency_ms = round(
            (time.perf_counter() - started) * 1000,
            1,
        )

        record_degraded(
            "vasuki_cloud",
            "startup_probe",
            exc,
            severity="warning",
            metadata={
                "latency_ms": latency_ms,
                "transport": str(
                    getattr(
                        settings,
                        "vasuki_cloud_transport",
                        "",
                    )
                    or ""
                ),
            },
        )

        _LOGGER.warning(
            "vasuki_cloud_startup_probe failed latency_ms=%s error_type=%s",
            latency_ms,
            type(exc).__name__,
        )

        return {
            "ran": True,
            "ok": False,
            "status": "failed",
            "latency_ms": latency_ms,
            "error_type": type(exc).__name__,
        }

    latency_ms = round(
        (time.perf_counter() - started) * 1000,
        1,
    )

    _LOGGER.info(
        "vasuki_cloud_startup_probe success latency_ms=%s",
        latency_ms,
    )

    return {
        "ran": True,
        "ok": True,
        "status": "success",
        "latency_ms": latency_ms,
    }