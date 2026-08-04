from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel

import app.main_v6 as v6
from app.auth import AuthUser, get_current_user
from app.services.comfyui_v1 import comfyui_health
from app.services.personal_memory import personal_memory_context
from app.services.pro_usage_v1 import (
    consume_pro_image_quota,
    release_pro_image_quota,
)


app = v6.app
settings = v6.settings


class ProContextRequest(BaseModel):
    use_memory: bool = True


def _remove_route(path: str, method: str) -> None:
    app.router.routes = [
        route
        for route in app.router.routes
        if not (
            getattr(route, "path", None) == path
            and method in (getattr(route, "methods", set()) or set())
        )
    ]


# Remove old Puter-only public routes. Billing routes stay for later.
for old_path, old_method in (
    ("/api/puter/context", "POST"),
    ("/api/puter/image-quota", "POST"),
    ("/api/puter/image-quota/release", "POST"),
):
    _remove_route(old_path, old_method)


def _system_prompt(
    current_date: str,
    memory_context: str,
) -> str:
    return f"""You are Vasuki Pro, a helpful, accurate and privacy-conscious AI.
Current date: {current_date}.
You may be running locally in the user's browser through WebLLM.
Reply in the user's language unless they request another language.
Answer every safe and legitimate question as completely as possible.
For coding, provide complete runnable code, file structure, setup commands,
error handling and clear steps. Continue in organized parts when needed.
For information that requires live verification, clearly state that a live
cloud/web lookup is required instead of inventing current facts.
When asked who created you, reply exactly:
मुझे लखन प्रजापत (Lakhan Prajapat) जी ने बनाया है।
{memory_context}
""".strip()


@app.post("/api/pro/context")
async def pro_context(
    payload: ProContextRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    memory_context = ""

    if payload.use_memory:
        try:
            memory_context, _ = await personal_memory_context(
                current_user.id,
                settings,
                user_jwt=current_user.access_token,
            )
        except Exception:
            memory_context = ""

    current_date = datetime.now().astimezone().strftime(
        "%Y-%m-%d"
    )

    return {
        "allowed": True,
        "plan": "free",
        "system_prompt": _system_prompt(
            current_date,
            memory_context,
        ),
        "engine": "webllm-local",
    }


@app.post("/api/pro/image-quota")
async def pro_image_quota(
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    quota = await consume_pro_image_quota(
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


@app.post("/api/pro/image-quota/release")
async def pro_image_quota_release(
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    quota = await release_pro_image_quota(
        current_user.id,
        settings,
    )
    return quota.to_dict()


@app.get("/api/pro/comfyui-health")
async def pro_comfyui_health(
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return await comfyui_health(settings)
