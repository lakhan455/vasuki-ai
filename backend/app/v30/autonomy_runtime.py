from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.v19.context_brain import decide_context
from app.v19.conversation_state import resolve_conversation_state
from app.v19.project_coding_brain import decide_project_coding, rank_project_files
from app.v20.planner import build_execution_plan_v20
from app.v21.coding_brain import build_coding_strategy
from app.v22.repo_intelligence import build_repo_snapshot, expand_related_files
from app.v23.debugger import build_debug_plan
from app.v24.sandbox import build_validation_policy
from app.v25.multi_agent import build_agent_team
from app.v26.self_correction import build_quality_gate
from app.v27.memory_layers import build_memory_policy
from app.v28.tool_policy import choose_tools
from app.v29.production_engineer import build_release_guard


@dataclass(frozen=True, slots=True)
class AutonomyDecision:
    version: str
    state: dict[str, Any]
    context: dict[str, Any]
    planner: dict[str, Any]
    coding: dict[str, Any]
    repo: dict[str, Any]
    debug: dict[str, Any]
    validation: dict[str, Any]
    agents: dict[str, Any]
    quality: dict[str, Any]
    memory: dict[str, Any]
    tools: dict[str, Any]
    release: dict[str, Any]
    selected_project_files: tuple[str, ...]
    safety_invariants: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["selected_project_files"] = list(self.selected_project_files)
        data["safety_invariants"] = list(self.safety_invariants)
        return data


def decide_autonomy(
    messages: list[dict[str, Any]],
    *,
    project_id: str = "",
    explicit_web: bool = False,
    research_mode: bool = False,
    project_files: list[dict[str, Any]] | None = None,
) -> AutonomyDecision:
    rows = project_files or []
    state = resolve_conversation_state(messages)
    context = decide_context(
        messages,
        explicit_web=explicit_web,
        research_mode=research_mode,
        project_id=project_id,
    )
    coding_decision = decide_project_coding(messages, project_id=project_id)
    initial = rank_project_files(
        state.active_request,
        rows,
        decision=coding_decision,
        limit=5,
    ) if rows and coding_decision.needs_project_files else []
    related = expand_related_files(rows, initial, limit=8) if rows and initial else initial
    repo = build_repo_snapshot(rows, related)
    planner = build_execution_plan_v20(messages, project_active=bool(project_id))
    coding = build_coding_strategy(messages, project_id=project_id)
    debug = build_debug_plan(state.active_request)
    validation = build_validation_policy("code" if coding_decision.coding_intent else context.task_type)
    agents = build_agent_team(
        coding=coding_decision.coding_intent,
        security_sensitive=coding_decision.needs_security_check,
        complex_task=context.task_type in {"coding", "reasoning", "research"} or len(state.active_request) > 1200,
    )
    quality = build_quality_gate(
        current_required=context.require_current,
        coding=coding_decision.coding_intent,
        destructive=planner.requires_user_confirmation,
    )
    memory = build_memory_policy(project_active=bool(project_id))
    tools = choose_tools(messages, project_active=bool(project_id), allow_web=context.allow_web)
    release = build_release_guard(state.active_request)

    return AutonomyDecision(
        version="v30",
        state=state.to_dict(),
        context=context.to_dict(),
        planner=planner.to_dict(),
        coding=coding.to_dict(),
        repo=repo.to_dict(),
        debug=debug.to_dict(),
        validation=validation.to_dict(),
        agents=agents.to_dict(),
        quality=quality.to_dict(),
        memory=memory.to_dict(),
        tools=tools.to_dict(),
        release=release.to_dict(),
        selected_project_files=tuple(related),
        safety_invariants=(
            "latest user intent has priority",
            "no silent persistent memory writes",
            "no blind database migration",
            "no arbitrary server-side code execution",
            "no deployment or destructive external action without confirmation",
            "do not claim validation ran without evidence",
            "do not expose hidden chain of thought",
        ),
    )


def build_autonomy_context(decision: AutonomyDecision) -> str:
    planner_steps = decision.planner.get("steps") or []
    tools = decision.tools.get("tools") or []
    selected = decision.selected_project_files
    lines = [
        "VASUKI V30 AUTONOMOUS RUNTIME CONTEXT:",
        f"Active request: {decision.state.get('active_request', '')}",
        f"Task: {decision.context.get('task_type', '')}; web_allowed={decision.context.get('allow_web', False)}.",
        "Execution plan: " + " -> ".join(str(step.get("step") or "") for step in planner_steps if isinstance(step, dict)),
        "Tool policy: " + ", ".join(str(x) for x in tools),
        f"Coding action: {decision.coding.get('action', 'not-coding')}.",
        f"Debug layer: {decision.debug.get('layer', 'backend')}.",
        "Memory priority: " + " -> ".join(str(x) for x in (decision.memory.get("priority") or [])),
        "Quality gates: " + " | ".join(str(x) for x in (decision.quality.get("checks") or [])),
    ]
    if selected:
        lines.append("Repository focus: " + " | ".join(selected))
    if decision.release.get("production_related"):
        lines.append(
            "PRODUCTION GUARD: do not deploy, migrate, delete, rotate secrets, or perform destructive external actions without explicit user confirmation. "
            "Require regression evidence and a rollback path."
        )
    lines.append(
        "Work from observable evidence. Keep changes minimal and compatible. "
        "If evidence is missing, identify what must be inspected instead of guessing."
    )
    return "\n".join(lines)[:12000]


def autonomy_runtime_health() -> dict[str, Any]:
    return {
        "version": "v30",
        "name": "Vasuki Unified Autonomous Runtime",
        "layers": [
            "v19.3-conversation-state",
            "v20-autonomous-planner",
            "v21-coding-brain",
            "v22-repository-intelligence",
            "v23-autonomous-debugger",
            "v24-safe-validation-sandbox-policy",
            "v25-multi-agent-coordination",
            "v26-self-correction-quality-gates",
            "v27-hierarchical-memory-controller",
            "v28-tool-selection-brain",
            "v29-production-engineer",
            "v30-unified-autonomy-runtime",
        ],
        "production_stream_integration": True,
        "db_migration_required": False,
        "new_api_key_required": False,
        "extra_provider_call_required": False,
        "silent_memory_write": False,
        "arbitrary_server_code_execution": False,
        "automatic_deploy_without_confirmation": False,
        "hidden_chain_of_thought_exposed": False,
    }
