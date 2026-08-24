from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.v17.provider_recovery import CodingProviderRecovery


def _settings(**overrides):
    values = {
        "groq_api_key": "x",
        "sambanova_api_key": None,
        "cerebras_api_key": None,
        "google_gemini_api": "x",
        "openrouter_api": "x",
        "mistral_ai_api": "x",
        "v17_provider_retry_rounds": 2,
        "v17_provider_attempt_timeout_seconds": 5,
        "v17_provider_transient_cooldown_seconds": 1,
        "v17_provider_quota_cooldown_seconds": 10,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_provider_recovery_falls_through_to_next_provider():
    async def scenario():
        calls = []

        async def fake(name, _messages, _settings):
            calls.append(name)
            if name == "groq":
                raise RuntimeError("503 upstream unavailable")
            return f"answer-from-{name}"

        pool = CodingProviderRecovery(
            _settings(),
            call_provider=fake,
        )
        answer, provider = await pool(
            [{"role": "user", "content": "build app"}]
        )

        assert provider != "groq"
        assert answer == f"answer-from-{provider}"
        assert calls[0] == "groq"
        assert len(calls) >= 2
        snap = pool.snapshot()
        assert snap["failures"]["groq"] == 1
        assert snap["successes"][provider] == 1

    asyncio.run(scenario())


def test_provider_recovery_does_not_return_shared_health_error():
    async def scenario():
        async def fake(name, _messages, _settings):
            raise RuntimeError(f"503 {name} down")

        pool = CodingProviderRecovery(
            _settings(v17_provider_retry_rounds=1),
            call_provider=fake,
        )

        with pytest.raises(RuntimeError) as caught:
            await pool(
                [{"role": "user", "content": "build app"}]
            )

        message = str(caught.value)
        assert "provider recovery exhausted" in message.lower()
        assert "No healthy AI provider" not in message
        assert "groq" in message
        assert "gemini" in message

    asyncio.run(scenario())


def test_moderation_is_not_cross_provider_bypassed():
    async def scenario():
        calls = []

        async def fake(name, _messages, _settings):
            calls.append(name)
            raise RuntimeError("moderation safety policy blocked")

        pool = CodingProviderRecovery(
            _settings(),
            call_provider=fake,
        )

        with pytest.raises(RuntimeError) as caught:
            await pool(
                [{"role": "user", "content": "unsafe"}]
            )

        assert "safety policy" in str(caught.value).lower()
        assert len(calls) == 1

    asyncio.run(scenario())
