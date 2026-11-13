from __future__ import annotations

import logging
import time
from typing import Any

from app.config import Settings
from app.services.chat import (
    _stream_vasuki_cloud_gradio,
    chat_vasuki_cloud,
)
from app.v50.telemetry import record_degraded


_LOGGER = logging.getLogger("uvicorn.error")

_CANARY_PROMPT = "Reply only with: VASUKI CLOUD READY"
_CANARY_EXPECTED = "VASUKI CLOUD READY"

_STREAM_CANARY_PROMPT = (
    "Reply only with: "
    "VASUKI STREAM READY ONE TWO THREE FOUR FIVE "
    "SIX SEVEN EIGHT NINE TEN"
)

_STREAM_CANARY_EXPECTED = (
    "VASUKI STREAM READY ONE TWO THREE FOUR FIVE "
    "SIX SEVEN EIGHT NINE TEN"
)


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


async def run_cloud_stream_startup_probe(
    settings: Settings,
) -> dict[str, Any]:
    """Verify actual multi-chunk Gradio streaming in production.

    No token, model output, or prompt content is written to logs.
    A failure never crashes application startup.
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
            "vasuki_cloud_stream_startup_probe",
            False,
        )
    )

    if not enabled or not probe_enabled:
        return {
            "ran": False,
            "ok": False,
            "status": "disabled",
        }

    transport = str(
        getattr(
            settings,
            "vasuki_cloud_transport",
            "",
        )
        or ""
    ).strip().casefold()

    if transport != "gradio":
        return {
            "ran": False,
            "ok": False,
            "status": "unsupported_transport",
        }

    started = time.perf_counter()
    first_chunk_ms = None
    chunks: list[str] = []

    try:
        async for chunk in _stream_vasuki_cloud_gradio(
            [
                {
                    "role": "user",
                    "content": _STREAM_CANARY_PROMPT,
                }
            ],
            settings,
            "",
            require_current=False,
            as_of=None,
        ):
            value = str(chunk or "")

            if not value:
                continue

            if first_chunk_ms is None:
                first_chunk_ms = round(
                    (
                        time.perf_counter()
                        - started
                    )
                    * 1000,
                    1,
                )

            chunks.append(value)

        answer = "".join(chunks)

        normalized = " ".join(
            answer.upper().split()
        )

        expected = " ".join(
            _STREAM_CANARY_EXPECTED.upper().split()
        )

        if expected not in normalized:
            raise RuntimeError(
                "Vasuki Cloud stream canary returned "
                "an unexpected response"
            )

        if len(chunks) < 2:
            raise RuntimeError(
                "Vasuki Cloud stream canary did not "
                "produce multiple chunks"
            )

    except Exception as exc:
        latency_ms = round(
            (
                time.perf_counter()
                - started
            )
            * 1000,
            1,
        )

        record_degraded(
            "vasuki_cloud",
            "stream_startup_probe",
            exc,
            severity="warning",
            metadata={
                "latency_ms": latency_ms,
                "first_chunk_ms": (
                    first_chunk_ms
                    if first_chunk_ms is not None
                    else ""
                ),
                "chunk_count": len(chunks),
                "transport": transport,
            },
        )

        _LOGGER.warning(
            "vasuki_cloud_stream_startup_probe "
            "failed latency_ms=%s first_chunk_ms=%s "
            "chunk_count=%s error_type=%s",
            latency_ms,
            first_chunk_ms,
            len(chunks),
            type(exc).__name__,
        )

        return {
            "ran": True,
            "ok": False,
            "status": "failed",
            "latency_ms": latency_ms,
            "first_chunk_ms": first_chunk_ms,
            "chunk_count": len(chunks),
            "error_type": type(exc).__name__,
        }

    latency_ms = round(
        (
            time.perf_counter()
            - started
        )
        * 1000,
        1,
    )

    _LOGGER.info(
        "vasuki_cloud_stream_startup_probe "
        "success latency_ms=%s first_chunk_ms=%s "
        "chunk_count=%s",
        latency_ms,
        first_chunk_ms,
        len(chunks),
    )

    return {
        "ran": True,
        "ok": True,
        "status": "success",
        "latency_ms": latency_ms,
        "first_chunk_ms": first_chunk_ms,
        "chunk_count": len(chunks),
    }
