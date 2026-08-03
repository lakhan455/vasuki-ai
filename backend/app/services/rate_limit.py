from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


INDIA_TIMEZONE = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True, slots=True)
class QuotaStatus:
    minute_limit: int
    minute_remaining: int
    daily_limit: int
    daily_remaining: int
    retry_after_seconds: int = 0


class QuotaExceeded(RuntimeError):
    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = max(1, int(retry_after_seconds))


class InMemoryChatQuota:
    """Dependency-free per-user guard for the free single Render instance."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._minute_events: dict[str, deque[float]] = defaultdict(deque)
        self._daily_counts: dict[tuple[str, str], int] = defaultdict(int)
        self._last_cleanup = 0.0

    @staticmethod
    def _day_key(now: datetime | None = None) -> str:
        current = now or datetime.now(INDIA_TIMEZONE)
        return current.astimezone(INDIA_TIMEZONE).date().isoformat()

    async def check(
        self,
        user_id: str,
        *,
        minute_limit: int,
        daily_limit: int,
    ) -> QuotaStatus:
        safe_minute_limit = max(1, int(minute_limit))
        safe_daily_limit = max(safe_minute_limit, int(daily_limit))
        now_monotonic = time.monotonic()
        day_key = self._day_key()

        async with self._lock:
            events = self._minute_events[user_id]
            cutoff = now_monotonic - 60.0
            while events and events[0] <= cutoff:
                events.popleft()

            if len(events) >= safe_minute_limit:
                retry_after = max(1, int(60.0 - (now_monotonic - events[0])))
                raise QuotaExceeded(
                    "Bahut zyada requests aa rahi hain. Thodi der baad dobara try karein.",
                    retry_after_seconds=retry_after,
                )

            daily_key = (day_key, user_id)
            current_daily = self._daily_counts[daily_key]
            if current_daily >= safe_daily_limit:
                now_india = datetime.now(INDIA_TIMEZONE)
                tomorrow = (
                    now_india.replace(hour=0, minute=0, second=0, microsecond=0)
                    + timedelta(days=1)
                )
                retry_after = max(1, int((tomorrow - now_india).total_seconds()))
                raise QuotaExceeded(
                    "Aaj ka free AI message quota poora ho gaya hai. Kal dobara try karein.",
                    retry_after_seconds=retry_after,
                )

            events.append(now_monotonic)
            self._daily_counts[daily_key] = current_daily + 1
            self._cleanup(now_monotonic, day_key)

            return QuotaStatus(
                minute_limit=safe_minute_limit,
                minute_remaining=max(0, safe_minute_limit - len(events)),
                daily_limit=safe_daily_limit,
                daily_remaining=max(
                    0,
                    safe_daily_limit - self._daily_counts[daily_key],
                ),
            )

    def _cleanup(self, now_monotonic: float, current_day: str) -> None:
        if now_monotonic - self._last_cleanup < 600.0:
            return

        self._last_cleanup = now_monotonic
        stale_daily_keys = [
            key for key in self._daily_counts if key[0] != current_day
        ]
        for key in stale_daily_keys:
            self._daily_counts.pop(key, None)

        empty_users = [
            user_id
            for user_id, events in self._minute_events.items()
            if not events
        ]
        for user_id in empty_users:
            self._minute_events.pop(user_id, None)

    async def reset_for_tests(self) -> None:
        async with self._lock:
            self._minute_events.clear()
            self._daily_counts.clear()
            self._last_cleanup = 0.0


CHAT_QUOTA = InMemoryChatQuota()
