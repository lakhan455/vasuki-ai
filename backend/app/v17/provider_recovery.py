from __future__ import annotations

# VASUKI_V17_1_PROVIDER_RECOVERY

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.services import chat as legacy
from app.services.router_v7 import configured_provider

ProviderCaller = Callable[
    [str, list[dict[str, Any]], Any],
    Awaitable[str],
]

CODE_PROVIDER_ORDER = (
    "groq",
    "gemini",
    "sambanova",
    "mistral",
    "openrouter",
    "cerebras",
)

_PROVIDER_GATES = {
    name: asyncio.Semaphore(1)
    for name in CODE_PROVIDER_ORDER
}


def configured_code_providers(settings: Any) -> list[str]:
    return [
        name
        for name in CODE_PROVIDER_ORDER
        if configured_provider(name, settings)
    ]


def _error_class(error: BaseException) -> str:
    message = str(error or "").casefold()
    if any(
        marker in message
        for marker in (
            "401",
            "402",
            "403",
            "unauthorized",
            "payment required",
            "not configured",
            "invalid api key",
            "invalid_api_key",
        )
    ):
        return "credential"
    if any(
        marker in message
        for marker in (
            "429",
            "quota",
            "rate limit",
            "rate_limit",
            "too many requests",
        )
    ):
        return "quota"
    if any(
        marker in message
        for marker in (
            "timeout",
            "timed out",
            "temporarily unavailable",
            "connection",
            "502",
            "503",
            "504",
            "empty",
        )
    ):
        return "transient"
    if "moderation" in message or "safety" in message:
        return "moderation"
    return "other"


def _safe_error(error: BaseException) -> str:
    value = str(error or "").strip().replace("\n", " ")
    return value[:700] or type(error).__name__


class CodingProviderRecovery:
    """
    Build-local provider recovery.

    Normal chat routing honors shared cooldowns. Autonomous builds can make
    several provider calls close together, so those shared cooldowns can
    temporarily exclude every provider mid-build. This pool calls configured
    providers explicitly, rotates the starting provider across batches, and
    uses a separate small build-local circuit breaker.
    """

    def __init__(
        self,
        settings: Any,
        *,
        call_provider: ProviderCaller | None = None,
    ) -> None:
        self.settings = settings
        self.providers = configured_code_providers(settings)
        self._caller = call_provider or self._default_call
        self._lock = asyncio.Lock()
        self._cursor = 0
        self._blocked_until: dict[str, float] = {}
        self._attempts: dict[str, int] = {}
        self._successes: dict[str, int] = {}
        self._failures: dict[str, int] = {}
        self._last_errors: dict[str, str] = {}
        self._used: list[str] = []

        if not self.providers:
            raise RuntimeError(
                "No coding AI provider is configured on the backend."
            )

    async def _default_call(
        self,
        name: str,
        messages: list[dict[str, Any]],
        settings: Any,
    ) -> str:
        return await legacy._call_provider(
            name,
            messages,
            settings,
            "",
            require_current=False,
            as_of=None,
            temperature=0.15,
        )

    async def _rotation(self) -> list[str]:
        async with self._lock:
            start = self._cursor % len(self.providers)
            self._cursor = (self._cursor + 1) % len(self.providers)
            return self.providers[start:] + self.providers[:start]

    def _cooldown_seconds(self, kind: str) -> float:
        if kind == "credential":
            return 3600.0
        if kind == "quota":
            return float(
                max(
                    10,
                    int(
                        getattr(
                            self.settings,
                            "v17_provider_quota_cooldown_seconds",
                            75,
                        )
                    ),
                )
            )
        if kind == "transient":
            return float(
                max(
                    1,
                    int(
                        getattr(
                            self.settings,
                            "v17_provider_transient_cooldown_seconds",
                            4,
                        )
                    ),
                )
            )
        if kind == "moderation":
            return 3600.0
        return 8.0

    async def _note_failure(
        self,
        name: str,
        error: BaseException,
    ) -> str:
        kind = _error_class(error)
        async with self._lock:
            self._failures[name] = self._failures.get(name, 0) + 1
            self._last_errors[name] = _safe_error(error)
            self._blocked_until[name] = (
                time.monotonic() + self._cooldown_seconds(kind)
            )
        return kind

    async def _note_success(self, name: str) -> None:
        async with self._lock:
            self._successes[name] = self._successes.get(name, 0) + 1
            self._blocked_until.pop(name, None)
            self._last_errors.pop(name, None)
            if name not in self._used:
                self._used.append(name)

    async def __call__(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[str, str]:
        rounds = max(
            1,
            min(
                3,
                int(
                    getattr(
                        self.settings,
                        "v17_provider_retry_rounds",
                        2,
                    )
                ),
            ),
        )
        timeout_seconds = float(
            max(
                8,
                int(
                    getattr(
                        self.settings,
                        "v17_provider_attempt_timeout_seconds",
                        38,
                    )
                ),
            )
        )

        errors: list[str] = []
        moderation_error: str | None = None

        for round_index in range(rounds):
            order = await self._rotation()
            now = time.monotonic()
            eligible = [
                name
                for name in order
                if now >= self._blocked_until.get(name, 0.0)
            ]

            if not eligible:
                waits = [
                    max(
                        0.0,
                        self._blocked_until.get(name, now) - now,
                    )
                    for name in order
                ]
                soonest = min(waits) if waits else 0.0
                if round_index + 1 < rounds and soonest <= 6.0:
                    await asyncio.sleep(
                        min(2.0, max(0.25, soonest))
                    )
                    continue

            for name in eligible:
                async with self._lock:
                    self._attempts[name] = (
                        self._attempts.get(name, 0) + 1
                    )

                try:
                    async with _PROVIDER_GATES[name]:
                        answer = await asyncio.wait_for(
                            self._caller(
                                name,
                                messages,
                                self.settings,
                            ),
                            timeout=timeout_seconds,
                        )

                    if not answer or not answer.strip():
                        raise RuntimeError(
                            "Provider returned an empty response."
                        )

                    await self._note_success(name)
                    return answer.strip(), name
                except Exception as exc:
                    kind = await self._note_failure(name, exc)
                    errors.append(
                        f"{name} [{kind}]: {_safe_error(exc)}"
                    )

                    # Never turn fallback into a moderation bypass.
                    if kind == "moderation":
                        moderation_error = _safe_error(exc)
                        break

            if moderation_error:
                break

            if round_index + 1 < rounds:
                await asyncio.sleep(0.65 + 0.45 * round_index)

        if moderation_error:
            raise RuntimeError(
                "Coding request was blocked by provider safety policy: "
                + moderation_error
            )

        details = " | ".join(errors[-8:])
        raise RuntimeError(
            "V17 provider recovery exhausted all configured coding "
            f"providers ({', '.join(self.providers)}). "
            + (details or "No provider returned usable code.")
        )

    def snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        return {
            "strategy": (
                "build-local-round-robin-explicit-provider-failover"
            ),
            "configured": list(self.providers),
            "used": list(self._used),
            "attempts": dict(self._attempts),
            "successes": dict(self._successes),
            "failures": dict(self._failures),
            "cooldowns_seconds": {
                name: max(0, round(until - now))
                for name, until in self._blocked_until.items()
                if until > now
            },
            "last_errors": dict(self._last_errors),
        }


def coding_provider_health(settings: Any) -> dict[str, Any]:
    return {
        "version": "v17.1",
        "configured": configured_code_providers(settings),
        "strategy": (
            "explicit-per-batch-failover-with-build-local-circuit-breaker"
        ),
        "shared_chat_cooldown_can_abort_build": False,
        "moderation_bypass": False,
    }
