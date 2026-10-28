from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from app.services.security_v9_phase6 import audit_event
from app.v11 import store
from app.v11.agents import consume_permission, grant_once, permission_level


_REQUEST_TTL_SECONDS = 600
_TOKEN_TTL_SECONDS = 300
_ALLOWED_PREFIXES = (
    "browser.",
    "project.",
    "files.",
    "github.",
    "deploy.",
    "message.",
    "memory.",
    "schedule.",
)


@dataclass
class ApprovalRequest:
    id: str
    user_id: str
    action: str
    args: dict[str, Any]
    summary: str
    risk: str
    status: str
    created_at_epoch: int
    expires_at_epoch: int
    decided_at_epoch: int | None = None

    def snapshot(self) -> dict[str, Any]:
        now = int(time.time())
        expired = self.expires_at_epoch < now and self.status == "pending"
        status = "expired" if expired else self.status
        return {
            "approval_id": self.id,
            "action": self.action,
            "summary": self.summary,
            "risk": self.risk,
            "status": status,
            "created_at_epoch": self.created_at_epoch,
            "expires_at_epoch": self.expires_at_epoch,
            "expires_in_seconds": max(0, self.expires_at_epoch - now),
            "one_time": True,
            "scope_locked": True,
        }


_REQUESTS: dict[str, ApprovalRequest] = {}


def _clean_action(value: str) -> str:
    action = str(value or "").strip().casefold()
    if not action or len(action) > 140:
        raise ValueError("Invalid approval action.")
    if not action.startswith(_ALLOWED_PREFIXES):
        raise ValueError("That action is not eligible for V77 approval.")
    if permission_level(action) == "read":
        raise ValueError("Read-only actions do not require V77 approval.")
    return action


def _safe_args(args: dict[str, Any] | None) -> dict[str, Any]:
    value = args if isinstance(args, dict) else {}
    if len(value) > 80:
        raise ValueError("Approval scope contains too many fields.")
    return value


def _risk_for(action: str, args: dict[str, Any]) -> str:
    joined = f"{action} {args}".casefold()
    if any(
        token in joined
        for token in (
            "payment",
            "bank",
            "password",
            "otp",
            "credential",
            "secret",
            "private_key",
        )
    ):
        return "critical"

    if bool(args.get("destructive")):
        return "high"

    if any(
        token in action
        for token in (
            "delete",
            "deploy",
            "github.file.write",
            "github.branch.create",
            "github.pr.create",
        )
    ):
        return "high"

    if action.startswith("project.") or action.startswith("browser."):
        return "medium"

    return "low"


def _purge_expired() -> None:
    now = int(time.time())
    stale = [
        request_id
        for request_id, request in _REQUESTS.items()
        if request.expires_at_epoch + 900 < now
    ]
    for request_id in stale:
        _REQUESTS.pop(request_id, None)


async def create_approval_request(
    settings: Any,
    *,
    user_id: str,
    action: str,
    args: dict[str, Any] | None,
    summary: str = "",
) -> dict[str, Any]:
    _purge_expired()
    clean_action = _clean_action(action)
    clean_args = _safe_args(args)
    now = int(time.time())

    request = ApprovalRequest(
        id=uuid.uuid4().hex,
        user_id=user_id,
        action=clean_action,
        args=clean_args,
        summary=str(summary or clean_action).strip()[:1200],
        risk=_risk_for(clean_action, clean_args),
        status="pending",
        created_at_epoch=now,
        expires_at_epoch=now + _REQUEST_TTL_SECONDS,
    )
    _REQUESTS[request.id] = request

    await audit_event(
        settings,
        actor_user_id=user_id,
        action="v77.approval.requested",
        outcome="pending",
        target_type="approval",
        target_id=request.id,
        metadata={
            "requested_action": request.action,
            "risk": request.risk,
            "summary": request.summary,
            "scope_keys": sorted(request.args.keys())[:40],
        },
    )
    return request.snapshot()


async def decide_approval_request(
    settings: Any,
    *,
    user_id: str,
    approval_id: str,
    approve: bool,
) -> dict[str, Any] | None:
    _purge_expired()
    request = _REQUESTS.get(str(approval_id or "").strip())
    if request is None or request.user_id != user_id:
        return None

    now = int(time.time())
    if request.expires_at_epoch < now:
        request.status = "expired"
        request.decided_at_epoch = now
        await audit_event(
            settings,
            actor_user_id=user_id,
            action="v77.approval.expired",
            outcome="expired",
            target_type="approval",
            target_id=request.id,
            metadata={
                "requested_action": request.action,
                "risk": request.risk,
            },
        )
        return request.snapshot()

    if request.status != "pending":
        return request.snapshot()

    if approve and request.risk == "critical":
        request.status = "blocked"
        request.decided_at_epoch = now
        payload = request.snapshot()
        await audit_event(
            settings,
            actor_user_id=user_id,
            action="v77.approval.blocked",
            outcome="blocked",
            target_type="approval",
            target_id=request.id,
            metadata={
                "requested_action": request.action,
                "risk": request.risk,
                "reason": "critical-risk actions are not approvable",
            },
        )
        return payload

    request.status = "approved" if approve else "denied"
    request.decided_at_epoch = now
    payload = request.snapshot()

    if approve:
        permission = await grant_once(
            settings,
            user_id=user_id,
            action=request.action,
            args=request.args,
            expires_seconds=_TOKEN_TTL_SECONDS,
        )
        payload["approval_token"] = str(permission.get("id") or "")
        payload["token_expires_at_epoch"] = int(
            permission.get("expires_at_epoch") or now + _TOKEN_TTL_SECONDS
        )

    await audit_event(
        settings,
        actor_user_id=user_id,
        action="v77.approval.decided",
        outcome=request.status,
        target_type="approval",
        target_id=request.id,
        metadata={
            "requested_action": request.action,
            "risk": request.risk,
            "one_time": True,
            "token_issued": bool(payload.get("approval_token")),
        },
    )
    return payload


async def consume_scoped_approval(
    settings: Any,
    *,
    user_id: str,
    action: str,
    args: dict[str, Any] | None,
    token: str | None,
) -> bool:
    clean_action = _clean_action(action)
    clean_args = _safe_args(args)

    allowed = await consume_permission(
        settings,
        user_id=user_id,
        action=clean_action,
        args=clean_args,
        token=token,
    )

    await audit_event(
        settings,
        actor_user_id=user_id,
        action="v77.approval.consumed",
        outcome="allowed" if allowed else "blocked",
        target_type="tool_action",
        target_id=clean_action,
        metadata={
            "risk": _risk_for(clean_action, clean_args),
            "scope_keys": sorted(clean_args.keys())[:40],
            "one_time": True,
        },
    )
    return bool(allowed)


def health_snapshot(settings: Any) -> dict[str, Any]:
    persistent_tokens = bool(store.configured(settings))
    return {
        "ok": True,
        "version": "v77",
        "name": "Vasuki Security & Approval Engine",
        "features": [
            "centralized-write-approval-policy",
            "one-time-scoped-approval-tokens",
            "action-and-args-fingerprint-lock",
            "approval-expiry",
            "deny-by-default",
            "risk-classification",
            "critical-risk-hard-block",
            "browser-action-gating",
            "project-write-gating",
            "persistent-security-audit-events",
            "custom-approval-dialog",
        ],
        "policy": {
            "read_actions": "automatic",
            "write_actions": "explicit-one-time-approval",
            "critical_risk_actions": "blocked",
            "scope_mutation_after_approval": "blocked",
            "token_reuse": "blocked",
            "request_ttl_seconds": _REQUEST_TTL_SECONDS,
            "token_ttl_seconds": _TOKEN_TTL_SECONDS,
        },
        "storage": {
            "approval_requests": "in-memory",
            "one_time_tokens": "existing-v11_tool_permissions",
            "one_time_tokens_persistent": persistent_tokens,
            "audit_log": "existing-audit_logs_v9",
            "new_database_migration_required": False,
        },
        "safety": {
            "credentials_and_payment_actions": "blocked",
            "external_write_without_valid_token": False,
            "fake_approval_state_allowed": False,
        },
        "new_database_migration_required": False,
        "new_api_key_required": False,
    }
