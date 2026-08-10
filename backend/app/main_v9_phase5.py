from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

import app.main_v9_phase4 as phase4
from app.auth import AuthUser, get_current_user
from app.services.account_v9 import (
    delete_account,
    export_chat,
    full_account_export,
    list_user_chats,
)
from app.services.maintenance_v9 import start_maintenance, stop_maintenance
from app.services.push_v9 import (
    push_config,
    subscribe_push,
    unsubscribe_push,
)
from app.services.storage_v9 import (
    cleanup_user_expired_artifacts,
    storage_usage,
)

app = phase4.app
settings = phase4.settings


class PushSubscriptionRequest(BaseModel):
    subscription: dict[str, Any] = Field(default_factory=dict)


class PushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(..., min_length=8, max_length=2000)


class AccountDeleteRequest(BaseModel):
    confirm_email: str = Field(..., min_length=3, max_length=320)
    confirmation: str = Field(..., min_length=5, max_length=80)


async def _phase5_startup() -> None:
    start_maintenance(settings)


async def _phase5_shutdown() -> None:
    await stop_maintenance()


app.router.add_event_handler("startup", _phase5_startup)
app.router.add_event_handler("shutdown", _phase5_shutdown)


@app.get("/api/account/v9/chats")
async def account_chats(
    limit: int = Query(200, ge=1, le=500),
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return {
            "chats": await list_user_chats(
                settings,
                user_id=current_user.id,
                limit=limit,
            )
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:1000]) from exc


@app.get("/api/account/v9/export/chat/{chat_id}")
async def account_export_chat(
    chat_id: str,
    format: str = Query("markdown", pattern="^(markdown|json)$"),
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            **await export_chat(
                settings,
                user_id=current_user.id,
                chat_id=chat_id,
                export_format="json" if format == "json" else "markdown",
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:1000]) from exc


@app.get("/api/account/v9/export/full")
async def account_export_full(
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "filename": "vasuki-ai-account-export.json",
            "mime_type": "application/json",
            "data": await full_account_export(
                settings,
                current_user=current_user,
            ),
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:1200]) from exc


@app.delete("/api/account/v9")
async def account_delete(
    payload: AccountDeleteRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await delete_account(
            settings,
            current_user=current_user,
            confirm_email=payload.confirm_email,
            confirmation=payload.confirmation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:1200]) from exc


@app.get("/api/storage/v9")
async def my_storage(
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "ok": True,
        **await storage_usage(settings, current_user.id),
    }


@app.post("/api/storage/v9/cleanup")
async def cleanup_my_storage(
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    result = await cleanup_user_expired_artifacts(
        settings,
        user_id=current_user.id,
        limit=300,
    )
    return {
        "ok": True,
        **result,
        "storage": await storage_usage(settings, current_user.id),
    }


@app.get("/api/push/v9/config")
async def browser_push_config(
    _current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {"ok": True, **push_config()}


@app.post("/api/push/v9/subscribe")
async def browser_push_subscribe(
    payload: PushSubscriptionRequest,
    request: Request,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        subscription = await subscribe_push(
            settings,
            user_id=current_user.id,
            subscription=payload.subscription,
            user_agent=request.headers.get("user-agent", ""),
        )
        return {"ok": True, "subscription": subscription}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:1000]) from exc


@app.delete("/api/push/v9/subscribe")
async def browser_push_unsubscribe(
    payload: PushUnsubscribeRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "ok": await unsubscribe_push(
            settings,
            user_id=current_user.id,
            endpoint=payload.endpoint,
        )
    }


@app.get("/health/v9-phase5")
async def health_v9_phase5() -> dict[str, Any]:
    config = push_config()
    return {
        "ok": True,
        "version": "v9-phase5",
        "chat_export": True,
        "full_account_export": True,
        "account_delete_flow": True,
        "file_storage_quotas": True,
        "auto_cleanup": True,
        "pwa_backend_support": True,
        "push_notifications": True,
        "push_configured": bool(config["configured"]),
        "offline_ui": True,
        "keyboard_shortcuts": True,
        "command_palette": True,
        "accessibility_upgrade": True,
        "push_note": "Browser push requires VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY on the backend.",
        "offline_note": "Offline mode provides the cached app shell; AI requests still require a network connection.",
    }
