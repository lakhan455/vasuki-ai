from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.services.puter_usage_v2 import (
    PuterImageQuota,
    consume_puter_image_quota,
    release_puter_image_quota,
)


async def reserve_image_slots(
    user_id: str,
    settings,
    *,
    count: int = 1,
) -> tuple[int, PuterImageQuota]:
    requested = max(
        1,
        min(50, int(count)),
    )

    reserved = 0
    latest: PuterImageQuota | None = None

    for _ in range(requested):
        quota = await consume_puter_image_quota(
            user_id,
            settings,
        )

        if not quota.allowed:
            if reserved:
                await release_image_slots(
                    user_id,
                    settings,
                    count=reserved,
                )

            raise HTTPException(
                status_code=429,
                detail=(
                    f"Daily image limit reached "
                    f"({quota.daily_limit}/day). "
                    "Please try again tomorrow."
                ),
            )

        reserved += 1
        latest = quota

    if latest is None:
        raise RuntimeError(
            "Image quota reservation failed."
        )

    return reserved, latest


async def release_image_slots(
    user_id: str,
    settings,
    *,
    count: int = 1,
) -> PuterImageQuota | None:
    releases = max(
        0,
        min(50, int(count)),
    )

    latest: PuterImageQuota | None = None

    for _ in range(releases):
        latest = await release_puter_image_quota(
            user_id,
            settings,
        )

    return latest


def quota_payload(
    quota: PuterImageQuota | None,
) -> dict[str, Any] | None:
    if quota is None:
        return None

    return quota.to_dict()
