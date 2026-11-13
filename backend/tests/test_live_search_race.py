from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from app.services import research


def _settings(**overrides):
    values = {
        "live_search_race_budget_seconds": 1.0,
        "live_search_race_min_sources": 4,
        "live_search_race_min_domains": 2,
        "live_search_crawler_hedge_delay_seconds": 0.0,
        "crawler_enabled": True,
        "tavily_api_key": "test",
        "exa_api": "test",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _rows(prefix: str, count: int = 4):
    return [
        {
            "title": f"{prefix} {index}",
            "url": f"https://source{index % 2}.example/{prefix}/{index}",
            "domain": f"source{index % 2}.example",
            "content": f"{prefix} evidence {index} " + ("x" * 100),
            "score": 1.0,
            "published_date": "2026-11-13T10:00:00+00:00",
        }
        for index in range(count)
    ]


def test_race_stops_after_fast_provider_has_enough_evidence():
    cancelled = {"slow": False}

    async def fast():
        await asyncio.sleep(0.01)
        return _rows("fast", 4)

    async def slow():
        try:
            await asyncio.sleep(5)
            return _rows("slow", 4)
        except asyncio.CancelledError:
            cancelled["slow"] = True
            raise

    started = time.perf_counter()
    rows, errors, providers = asyncio.run(
        research._run_live_search_race(
            [("tavily", fast()), ("crawler", slow())],
            _settings(),
            6,
        )
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 0.5
    assert len(rows) == 4
    assert errors == []
    assert providers == {"tavily"}
    assert cancelled["slow"] is True


def test_race_uses_crawler_when_api_sources_are_empty():
    async def empty():
        await asyncio.sleep(0.01)
        return []

    async def crawler():
        await asyncio.sleep(0.02)
        return _rows("crawler", 4)

    rows, errors, providers = asyncio.run(
        research._run_live_search_race(
            [
                ("tavily", empty()),
                ("exa", empty()),
                ("crawler", crawler()),
            ],
            _settings(),
            6,
        )
    )

    assert len(rows) == 4
    assert errors == []
    assert providers == {"crawler"}


def test_race_hard_budget_cancels_hanging_source():
    cancelled = {"value": False}

    async def hanging():
        try:
            await asyncio.sleep(5)
            return []
        except asyncio.CancelledError:
            cancelled["value"] = True
            raise

    started = time.perf_counter()
    rows, errors, providers = asyncio.run(
        research._run_live_search_race(
            [("crawler", hanging())],
            _settings(live_search_race_budget_seconds=1.0),
            6,
        )
    )
    elapsed = time.perf_counter() - started

    assert 0.8 <= elapsed < 1.5
    assert rows == []
    assert errors == []
    assert providers == set()
    assert cancelled["value"] is True
