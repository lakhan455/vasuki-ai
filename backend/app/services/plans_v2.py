from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.auth import AuthUser
from app.config import Settings
from app.services import plans_v1 as paid


PlanStatus = paid.PlanStatus
process_razorpay_webhook = paid.process_razorpay_webhook
verify_razorpay_payment = paid.verify_razorpay_payment


async def get_plan_status(
    user: AuthUser,
    settings: Settings,
) -> PlanStatus:
    owner = paid.is_owner(user, settings)
    return PlanStatus(
        plan="owner" if owner else "free",
        is_owner=owner,
        puter_access=True,
        pro_expires_at=None,
        amount_paise=0,
        plan_days=0,
    )


async def require_puter_access(
    user: AuthUser,
    settings: Settings,
) -> PlanStatus:
    status = await get_plan_status(user, settings)
    if not status.puter_access:
        raise HTTPException(
            status_code=403,
            detail="Puter access is locked.",
        )
    return status


async def create_razorpay_order(
    user: AuthUser,
    settings: Settings,
) -> dict[str, Any]:
    raise HTTPException(
        status_code=410,
        detail="Paid plan checkout is no longer available.",
    )
