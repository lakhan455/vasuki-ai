from __future__ import annotations

import asyncio

import pytest

from app.config import Settings
from app.services.chat_v4 import provider_diagnostics_snapshot, safe_error
from app.services.rate_limit import InMemoryChatQuota, QuotaExceeded


def test_safe_error_redacts_secret_like_values() -> None:
    cleaned = safe_error(RuntimeError("api_key=super-secret-value token=abc123"))
    assert "super-secret-value" not in cleaned
    assert "[redacted]" in cleaned


def test_provider_diagnostics_never_exposes_keys() -> None:
    settings = Settings(
        groq_api_key="private-key",
        google_gemini_api="another-private-key",
    )
    snapshot = provider_diagnostics_snapshot(settings)
    encoded = repr(snapshot)
    assert "private-key" not in encoded
    assert "another-private-key" not in encoded
    assert snapshot["groq"]["configured"] is True
    assert snapshot["gemini"]["configured"] is True


def test_minute_quota_blocks_extra_request() -> None:
    async def scenario() -> None:
        quota = InMemoryChatQuota()
        await quota.check("user-1", minute_limit=2, daily_limit=10)
        await quota.check("user-1", minute_limit=2, daily_limit=10)
        with pytest.raises(QuotaExceeded):
            await quota.check("user-1", minute_limit=2, daily_limit=10)

    asyncio.run(scenario())


def test_daily_quota_blocks_extra_request() -> None:
    async def scenario() -> None:
        quota = InMemoryChatQuota()
        await quota.check("user-2", minute_limit=10, daily_limit=2)
        await quota.check("user-2", minute_limit=10, daily_limit=2)
        with pytest.raises(QuotaExceeded):
            await quota.check("user-2", minute_limit=10, daily_limit=2)

    asyncio.run(scenario())
