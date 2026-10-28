from __future__ import annotations

import asyncio
from pathlib import Path

from app.v77 import approval_engine


class Settings:
    pass


def test_v77_health_policy_is_deny_by_default(monkeypatch):
    monkeypatch.setattr(approval_engine.store, "configured", lambda settings: True)
    health = approval_engine.health_snapshot(Settings())
    assert health["version"] == "v77"
    assert health["policy"]["write_actions"] == "explicit-one-time-approval"
    assert health["policy"]["critical_risk_actions"] == "blocked"
    assert health["policy"]["token_reuse"] == "blocked"
    assert health["storage"]["new_database_migration_required"] is False
    assert health["safety"]["external_write_without_valid_token"] is False


def test_v77_approval_is_scoped_one_time_and_audited(monkeypatch):
    issued: list[dict] = []
    consumed: list[dict] = []
    audits: list[dict] = []

    async def fake_grant(settings, *, user_id, action, args, expires_seconds):
        row = {
            "id": "token-123",
            "user_id": user_id,
            "action": action,
            "args": args,
            "expires_at_epoch": 9999999999,
        }
        issued.append(row)
        return row

    async def fake_consume(settings, *, user_id, action, args, token):
        consumed.append(
            {"user_id": user_id, "action": action, "args": args, "token": token}
        )
        return token == "token-123"

    async def fake_audit(settings, **kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(approval_engine, "grant_once", fake_grant)
    monkeypatch.setattr(approval_engine, "consume_permission", fake_consume)
    monkeypatch.setattr(approval_engine, "audit_event", fake_audit)

    async def scenario():
        pending = {
            "type": "project.code.apply",
            "project_id": "p1",
            "change_count": 2,
            "paths": ["a.py", "b.py"],
            "destructive": False,
        }
        request = await approval_engine.create_approval_request(
            Settings(),
            user_id="u1",
            action="project.code.apply",
            args=pending,
            summary="Apply two project changes",
        )
        decision = await approval_engine.decide_approval_request(
            Settings(),
            user_id="u1",
            approval_id=request["approval_id"],
            approve=True,
        )
        assert decision is not None
        allowed = await approval_engine.consume_scoped_approval(
            Settings(),
            user_id="u1",
            action="project.code.apply",
            args=pending,
            token=decision.get("approval_token"),
        )
        return request, decision, allowed

    request, decision, allowed = asyncio.run(scenario())
    assert request["status"] == "pending"
    assert decision["status"] == "approved"
    assert decision["approval_token"] == "token-123"
    assert allowed is True
    assert len(issued) == 1
    assert len(consumed) == 1
    assert len(audits) >= 3


def test_v77_denial_does_not_issue_token(monkeypatch):
    issued = []

    async def fake_grant(*args, **kwargs):
        issued.append(True)
        return {"id": "should-not-exist"}

    async def fake_audit(*args, **kwargs):
        return None

    monkeypatch.setattr(approval_engine, "grant_once", fake_grant)
    monkeypatch.setattr(approval_engine, "audit_event", fake_audit)

    async def scenario():
        request = await approval_engine.create_approval_request(
            Settings(),
            user_id="u-deny",
            action="browser.click",
            args={"type": "browser.click", "target_id": "x"},
            summary="Click button",
        )
        return await approval_engine.decide_approval_request(
            Settings(),
            user_id="u-deny",
            approval_id=request["approval_id"],
            approve=False,
        )

    decision = asyncio.run(scenario())
    assert decision is not None
    assert decision["status"] == "denied"
    assert "approval_token" not in decision
    assert issued == []


def test_v77_critical_risk_is_hard_blocked(monkeypatch):
    issued = []

    async def fake_grant(*args, **kwargs):
        issued.append(True)
        return {"id": "bad"}

    async def fake_audit(*args, **kwargs):
        return None

    monkeypatch.setattr(approval_engine, "grant_once", fake_grant)
    monkeypatch.setattr(approval_engine, "audit_event", fake_audit)

    async def scenario():
        request = await approval_engine.create_approval_request(
            Settings(),
            user_id="u-critical",
            action="browser.fill",
            args={
                "type": "browser.fill",
                "target_id": "payment-card",
                "reason": "payment credential",
            },
            summary="Fill payment field",
        )
        return await approval_engine.decide_approval_request(
            Settings(),
            user_id="u-critical",
            approval_id=request["approval_id"],
            approve=True,
        )

    decision = asyncio.run(scenario())
    assert decision is not None
    assert decision["status"] == "blocked"
    assert "approval_token" not in decision
    assert issued == []


def test_v77_production_wiring_and_custom_dialog_present():
    repo = Path(__file__).resolve().parents[2]
    main = (repo / "backend/app/main_v11.py").read_text(encoding="utf-8")
    api = (repo / "frontend/lib/api.ts").read_text(encoding="utf-8")
    chat = (repo / "frontend/components/ChatApp.tsx").read_text(encoding="utf-8")
    dialog = (repo / "frontend/components/ApprovalDialogV77.tsx").read_text(
        encoding="utf-8"
    )

    assert '"/health/v77"' in main
    assert '"/api/v77/approvals"' in main
    assert "v77_consume_scoped_approval" in main
    assert "approval_token" in main
    assert "createApprovalV77" in api
    assert "decideApprovalV77" in api
    assert "reviewApprovalV77" in chat
    assert "ApprovalDialogV77" in chat
    assert chat.count("window.confirm(") == 1
    assert "Approve once" in dialog
    assert "Deny" in dialog
