from pathlib import Path

from app.v19.conversation_state import resolve_conversation_state
from app.v20.planner import build_execution_plan_v20
from app.v21.coding_brain import build_coding_strategy
from app.v22.repo_intelligence import build_repo_snapshot, expand_related_files
from app.v23.debugger import build_debug_plan
from app.v24.sandbox import build_validation_policy, is_command_safe
from app.v25.multi_agent import build_agent_team
from app.v26.self_correction import build_quality_gate
from app.v27.memory_layers import build_memory_policy
from app.v28.tool_policy import choose_tools
from app.v29.production_engineer import build_release_guard
from app.v30.autonomy_runtime import autonomy_runtime_health, build_autonomy_context, decide_autonomy


MESSAGES = [
    {"role": "user", "content": "FastAPI login endpoint returns AttributeError after deploy"},
    {"role": "assistant", "content": "I can inspect it."},
    {"role": "user", "content": "isko fix karo"},
]


def test_v19_3_followup_state():
    state = resolve_conversation_state(MESSAGES)
    assert state.is_followup is True
    assert "FastAPI login endpoint" in state.active_request


def test_v20_planner_has_inspect_for_project_code():
    plan = build_execution_plan_v20(MESSAGES, project_active=True)
    assert any(step.step == "inspect" for step in plan.steps)


def test_v21_coding_strategy_preserves_interfaces():
    strategy = build_coding_strategy(MESSAGES, project_id="p1")
    assert strategy.inspect_first is True
    assert strategy.preserve_interfaces is True


def test_v22_repo_related_files():
    rows = [
        {"path": "backend/a.py", "language": "python", "metadata": {"signals": {"symbols": ["login"], "imports": ["backend.b"], "routes": ["/login"]}}},
        {"path": "backend/b.py", "language": "python", "metadata": {"signals": {"symbols": ["backend.b"], "imports": ["login"], "routes": []}}},
        {"path": "render.yaml", "language": "yaml", "metadata": {"signals": {}}},
    ]
    related = expand_related_files(rows, ["backend/a.py"], limit=3)
    assert "backend/a.py" in related
    snap = build_repo_snapshot(rows, related)
    assert snap.files == 3
    assert "/login" in snap.routes


def test_v23_debugger_detects_deployment():
    plan = build_debug_plan("Render deploy failed with AttributeError")
    assert plan.layer == "deployment"
    assert "AttributeError" in plan.signatures


def test_v24_blocks_destructive_command():
    assert is_command_safe("python -m pytest -q") is True
    assert is_command_safe("git reset --hard HEAD~1") is False
    assert build_validation_policy("code").arbitrary_execution_enabled is False


def test_v25_security_role():
    team = build_agent_team(coding=True, security_sensitive=True, complex_task=True)
    assert any(role.role == "security-reviewer" for role in team.roles)
    assert team.extra_provider_calls_required is False


def test_v26_quality_gate_code_evidence():
    gate = build_quality_gate(current_required=False, coding=True, destructive=False)
    assert "validation claims have evidence" in gate.checks


def test_v27_memory_no_silent_write():
    policy = build_memory_policy(project_active=True)
    assert policy.write_policy == "no-new-persistent-write"
    assert policy.priority[0] == "current-conversation"


def test_v28_tool_selection_project_code():
    decision = choose_tools(MESSAGES, project_active=True, allow_web=False)
    assert "project-kb" in decision.tools
    assert decision.external_side_effect_allowed is False


def test_v29_release_guard_requires_confirmation():
    guard = build_release_guard("Deploy this to production on Render")
    assert guard.production_related is True
    assert guard.confirmation_required_for_deploy is True
    assert "never apply database migration blindly" in guard.migration_policy


def test_v30_unified_runtime_and_context():
    rows = [
        {"path": "backend/app/main_v5.py", "language": "python", "metadata": {"signals": {"symbols": ["chat_stream_v5"], "imports": [], "routes": ["/api/chat/stream"]}}},
        {"path": "render.yaml", "language": "yaml", "metadata": {"signals": {}}},
    ]
    decision = decide_autonomy(MESSAGES, project_id="p1", project_files=rows)
    assert decision.version == "v30"
    assert decision.coding["inspect_first"] is True
    context = build_autonomy_context(decision)
    assert "VASUKI V30 AUTONOMOUS RUNTIME CONTEXT" in context
    assert "do not deploy" in context.casefold()


def test_v30_health_safety_contract():
    health = autonomy_runtime_health()
    assert health["db_migration_required"] is False
    assert health["new_api_key_required"] is False
    assert health["extra_provider_call_required"] is False
    assert health["silent_memory_write"] is False
    assert health["arbitrary_server_code_execution"] is False
    assert health["automatic_deploy_without_confirmation"] is False


def test_main_v11_v30_integration_present():
    backend = Path(__file__).resolve().parents[1]
    source = (backend / "app" / "main_v11.py").read_text(encoding="utf-8")
    assert "VASUKI_V30_AUTONOMY_RUNTIME_INTEGRATION" in source
    assert "v10.legacy._private_context = _v30_private_context" in source
    assert '@app.get("/health/v30")' in source


def test_frontend_shows_v30_without_status_badges():
    repo = Path(__file__).resolve().parents[2]
    source = (repo / "frontend" / "components" / "ChatApp.tsx").read_text(encoding="utf-8")
    assert (
        "Vasuki Core · V30 Autonomous Runtime · online" in source
        or "Vasuki Core · V40 Advanced Creator Runtime · online" in source
    )
    assert "pv-living-mind-badge" not in source
    assert '<div className="pv-header-right">' not in source
