from __future__ import annotations

import asyncio
from typing import Any

from app.config import Settings
from app.services.artifacts_v8 import cleanup_expired

_task: asyncio.Task[Any] | None = None


async def maintenance_loop(settings: Settings) -> None:
    while True:
        try:
            await cleanup_expired(settings, limit=200)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(60 * 60)


def start_maintenance(settings: Settings) -> None:
    global _task
    if _task and not _task.done():
        return
    _task = asyncio.create_task(maintenance_loop(settings))


async def stop_maintenance() -> None:
    global _task
    task = _task
    _task = None
    if not task:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
