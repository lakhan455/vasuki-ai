from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

import app.main_v5 as v5
from app.auth import AuthUser, get_current_user
from app.services.personal_memory import personal_memory_context
from app.services.puter_usage_v2 import (
    consume_puter_image_quota,
    release_puter_image_quota,
)
from app.services.plans_v2 import (
    create_razorpay_order,
    get_plan_status,
    process_razorpay_webhook,
    require_puter_access,
    verify_razorpay_payment,
)

app = v5.app
settings = v5.settings


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str = Field(min_length=4, max_length=120)
    razorpay_payment_id: str = Field(min_length=4, max_length=120)
    razorpay_signature: str = Field(min_length=16, max_length=300)


class PuterContextRequest(BaseModel):
    use_memory: bool = True


@app.get("/api/account/plan")
async def account_plan(current_user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    return (await get_plan_status(current_user, settings)).to_dict()


@app.post("/api/billing/create-order")
async def billing_create_order(current_user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    return await create_razorpay_order(current_user, settings)


@app.post("/api/billing/verify")
async def billing_verify(
    payload: VerifyPaymentRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return await verify_razorpay_payment(
        current_user,
        settings,
        order_id=payload.razorpay_order_id,
        payment_id=payload.razorpay_payment_id,
        signature=payload.razorpay_signature,
    )


@app.post("/api/billing/webhook")
async def billing_webhook(
    request: Request,
    x_razorpay_signature: str = Header(default="", alias="X-Razorpay-Signature"),
) -> dict[str, Any]:
    return await process_razorpay_webhook(await request.body(), x_razorpay_signature, settings)



@app.post("/api/puter/image-quota")
async def puter_image_quota(
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    await require_puter_access(current_user, settings)
    quota = await consume_puter_image_quota(
        current_user.id,
        settings,
    )

    if not quota.allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Aaj ki {quota.daily_limit} Vasuki Pro images "
                "complete ho gayi hain. Kal dobara generate karein."
            ),
        )

    return quota.to_dict()


@app.post("/api/puter/image-quota/release")
async def puter_image_quota_release(
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    await require_puter_access(current_user, settings)
    quota = await release_puter_image_quota(
        current_user.id,
        settings,
    )
    return quota.to_dict()


@app.post("/api/puter/context")
async def puter_context(
    payload: PuterContextRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    status = await require_puter_access(current_user, settings)
    memory_context = ""
    if payload.use_memory:
        memory_context, _ = await personal_memory_context(
            current_user.id,
            settings,
            user_jwt=current_user.access_token,
        )
    current_date = datetime.now().astimezone().strftime("%Y-%m-%d")
    system_prompt = f"""You are Vasuki AI, a helpful and accurate assistant.
Current date: {current_date}.
Reply in the user's language unless they request another language.
Answer every safe and legitimate question as completely as possible.
For coding, provide complete runnable code, file structure, setup commands,
error handling, and clear steps. Do not stop merely because the answer is long;
continue in organized parts when needed.
Never invent live facts. Say when verification is required.
When asked who created you, reply exactly:
मुझे लखन प्रजापत (Lakhan Prajapat) जी ने बनाया है।
{memory_context}
"""
    return {
        "allowed": True,
        "plan": status.plan,
        "system_prompt": system_prompt.strip(),
        "note": "Puter usage runs on the signed-in user's Puter account and allowance.",
    }
