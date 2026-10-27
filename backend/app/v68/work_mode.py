from __future__ import annotations

import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.services.chat_v10 import route_chat_v10
from app.services.coding_agent_v9 import generate_coding_plan
from app.services.project_kb_v9 import (
    apply_project_changes,
    build_project_codebase_map,
)
from app.v11.agents import safe_calculate
from app.v11.research import run_research
from app.v13.autonomy import build_execution_plan


TERMINAL_STATES = {"succeeded", "blocked", "failed", "cancelled"}


@dataclass
class WorkJob:
    id: str
    user_id: str
    goal: str
    project_id: str | None = None
    status: str = "queued"
    stage: str = "queued"
    progress: int = 0
    message: str = "Work queued"
    error: str = ""
    plan: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    pending_action: dict[str, Any] | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    task: asyncio.Task | None = None
    approval_event: asyncio.Event = field(default_factory=asyncio.Event)
    approval_decision: str = ""

    def snapshot(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.status != "failed",
            "job_id": self.id,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "message": self.message,
            "error": self.error or None,
            "goal": self.goal,
            "project_id": self.project_id,
            "plan": self.plan,
            "pending_action": self.pending_action,
            "events": list(self.events[-30:]),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.status in TERMINAL_STATES and self.result is not None:
            payload["result"] = self.result
        return payload


_JOBS: dict[str, WorkJob] = {}
_LOCK = asyncio.Lock()


def _event(
    job: WorkJob,
    *,
    step: str,
    state: str,
    detail: str,
    tool: str = "",
    evidence: dict[str, Any] | None = None,
) -> None:
    job.events.append(
        {
            "at": time.time(),
            "step": step,
            "state": state,
            "detail": str(detail or "")[:800],
            "tool": str(tool or "")[:120],
            "evidence": evidence or {},
        }
    )
    if len(job.events) > 60:
        del job.events[:-60]


async def _set_progress(
    job: WorkJob,
    *,
    stage: str,
    progress: int,
    message: str,
) -> None:
    async with _LOCK:
        current = _JOBS.get(job.id)
        if not current:
            return
        current.stage = stage[:80]
        current.progress = max(0, min(100, int(progress)))
        current.message = message[:500]
        current.updated_at = time.time()


def _extract_expression(goal: str) -> str:
    value = str(goal or "")
    matches = re.findall(r"[0-9().+\-*/%\s]{3,}", value)
    candidates = [
        re.sub(r"\s+", " ", item).strip()
        for item in matches
        if any(ch.isdigit() for ch in item)
        and any(ch in "+-*/%" for ch in item)
    ]
    return max(candidates, key=len) if candidates else ""


def work_contract(goal: str, *, project_id: str | None = None) -> dict[str, Any]:
    plan = build_execution_plan(
        [{"role": "user", "content": str(goal or "").strip()}],
        require_current=False,
    ).to_dict()
    mode = str(plan.get("mode") or "direct")

    support = {
        "research": "real_live_research",
        "code_agent": (
            "real_project_patch_with_approval"
            if project_id
            else "requires_active_project"
        ),
        "calculator": "real_deterministic_calculation",
        "direct": "real_model_deliverable",
        "artifact": "existing_artifact_workflow_outside_v68",
        "image": "existing_image_workflow_outside_v68",
    }.get(mode, "real_model_deliverable")

    return {
        "goal": str(goal or "").strip(),
        "mode": mode,
        "support": support,
        "plan": plan,
        "no_fake_execution": True,
        "server_side_tests_claimed": False,
    }


async def _run_research_job(job: WorkJob, settings: Any) -> None:
    await _set_progress(
        job,
        stage="researching",
        progress=28,
        message="Searching independent live sources",
    )
    _event(
        job,
        step="research",
        state="running",
        detail="Started deep research with live evidence collection.",
        tool="research.run",
    )

    report = await run_research(job.goal, settings)
    sources = report.get("sources") if isinstance(report, dict) else []
    sources = sources if isinstance(sources, list) else []

    if not sources:
        _event(
            job,
            step="research",
            state="blocked",
            detail="Research completed without usable live sources; no factual answer was guessed.",
            tool="research.run",
            evidence={"source_count": 0},
        )
        job.status = "blocked"
        job.stage = "blocked"
        job.progress = 100
        job.message = "Live research returned no usable evidence"
        job.result = {
            "answer": (
                "Work Mode could not verify this task because live research "
                "returned no usable sources. No factual answer was guessed."
            ),
            "sources": [],
            "execution_proof": {
                "executed_tools": ["research.run"],
                "source_count": 0,
                "claim": "blocked-no-evidence",
            },
        }
        return

    answer = str(report.get("answer") or "").strip()
    _event(
        job,
        step="research",
        state="completed",
        detail=f"Research returned {len(sources)} cited source(s).",
        tool="research.run",
        evidence={"source_count": len(sources)},
    )
    job.status = "succeeded"
    job.stage = "ready"
    job.progress = 100
    job.message = "Research work completed"
    job.result = {
        "answer": answer or "Research completed.",
        "sources": sources,
        "research": report,
        "execution_proof": {
            "executed_tools": ["research.run"],
            "source_count": len(sources),
            "citation_check": report.get("citation_check") or {},
        },
    }


async def _run_project_code_job(job: WorkJob, settings: Any) -> None:
    if not job.project_id:
        _event(
            job,
            step="project",
            state="blocked",
            detail="Coding work requires an active Vasuki Project with uploaded project files.",
        )
        job.status = "blocked"
        job.stage = "needs-project"
        job.progress = 100
        job.message = "Open a Project before running project code work"
        job.result = {
            "answer": (
                "This coding task was not executed because Work Mode needs an "
                "active Vasuki Project with project files. Open/select a Project, "
                "upload the relevant code, then run the task again."
            ),
            "sources": [],
            "execution_proof": {
                "executed_tools": [],
                "blocked_reason": "missing-active-project",
            },
        }
        return

    await _set_progress(
        job,
        stage="inspecting-project",
        progress=22,
        message="Inspecting project files and codebase map",
    )
    code_map = await build_project_codebase_map(
        settings,
        user_id=job.user_id,
        project_id=job.project_id,
    )
    _event(
        job,
        step="inspect-project",
        state="completed",
        detail="Project codebase map loaded.",
        tool="project.kb.map",
        evidence={
            "files": len(code_map.get("files") or [])
            if isinstance(code_map, dict)
            else 0
        },
    )

    await _set_progress(
        job,
        stage="planning-patch",
        progress=48,
        message="Generating a targeted project patch",
    )
    patch = await generate_coding_plan(
        settings,
        user_id=job.user_id,
        project_id=job.project_id,
        instruction=job.goal,
        target_paths=[],
        mode="patch",
    )
    plan = patch.get("plan") if isinstance(patch, dict) else {}
    plan = plan if isinstance(plan, dict) else {}
    changes = plan.get("changes") if isinstance(plan, dict) else []
    changes = changes if isinstance(changes, list) else []

    _event(
        job,
        step="plan-patch",
        state="completed",
        detail=f"Generated {len(changes)} proposed project change(s).",
        tool="project.code.patch",
        evidence={
            "change_count": len(changes),
            "paths": [
                str(item.get("path") or "")
                for item in changes[:20]
                if isinstance(item, dict)
            ],
        },
    )

    if not changes:
        job.status = "succeeded"
        job.stage = "ready"
        job.progress = 100
        job.message = "No file changes were required"
        job.result = {
            "answer": str(plan.get("summary") or "No project file changes were proposed."),
            "sources": [],
            "patch": patch,
            "execution_proof": {
                "executed_tools": ["project.kb.map", "project.code.patch"],
                "files_changed": 0,
                "server_side_tests_run": False,
            },
        }
        return

    paths = [
        str(item.get("path") or "")
        for item in changes
        if isinstance(item, dict) and str(item.get("path") or "").strip()
    ]
    destructive = any(
        str(item.get("action") or "").casefold() == "delete"
        for item in changes
        if isinstance(item, dict)
    )

    async with _LOCK:
        current = _JOBS.get(job.id)
        if not current:
            return
        current.status = "awaiting_approval"
        current.stage = "approval"
        current.progress = 68
        current.message = "Approval required before project files are changed"
        current.pending_action = {
            "type": "project.code.apply",
            "project_id": job.project_id,
            "change_count": len(changes),
            "paths": paths[:30],
            "destructive": destructive,
            "summary": str(plan.get("summary") or "")[:1000],
        }
        current.updated_at = time.time()

    _event(
        job,
        step="approval",
        state="waiting",
        detail="Explicit user approval is required before applying project file changes.",
        tool="project.code.apply",
        evidence={
            "change_count": len(changes),
            "destructive": destructive,
            "paths": paths[:20],
        },
    )

    try:
        await asyncio.wait_for(job.approval_event.wait(), timeout=900.0)
    except asyncio.TimeoutError:
        job.status = "cancelled"
        job.stage = "approval-expired"
        job.progress = 100
        job.message = "Approval expired; no project files were changed"
        job.pending_action = None
        job.result = {
            "answer": "Approval expired. No project files were changed.",
            "sources": [],
            "execution_proof": {
                "executed_tools": ["project.kb.map", "project.code.patch"],
                "project_code_apply": "not-executed",
            },
        }
        return

    if job.approval_decision != "approve":
        job.status = "cancelled"
        job.stage = "cancelled"
        job.progress = 100
        job.message = "Project changes were not approved"
        job.pending_action = None
        job.result = {
            "answer": "Work stopped before file changes because approval was not granted.",
            "sources": [],
            "execution_proof": {
                "executed_tools": ["project.kb.map", "project.code.patch"],
                "project_code_apply": "not-executed",
            },
        }
        _event(
            job,
            step="approval",
            state="rejected",
            detail="User rejected the proposed project changes.",
            tool="project.code.apply",
        )
        return

    await _set_progress(
        job,
        stage="applying-patch",
        progress=82,
        message="Applying approved changes to project files",
    )
    applied = await apply_project_changes(
        settings,
        user_id=job.user_id,
        project_id=job.project_id,
        changes=changes,
    )
    job.pending_action = None

    _event(
        job,
        step="apply-patch",
        state="completed",
        detail=f"Applied {len(changes)} approved project change(s).",
        tool="project.code.apply",
        evidence={"paths": paths[:20], "change_count": len(changes)},
    )

    job.status = "succeeded"
    job.stage = "ready"
    job.progress = 100
    job.message = "Approved project changes applied"
    job.result = {
        "answer": (
            str(plan.get("summary") or "").strip()
            or f"Applied {len(changes)} approved project change(s)."
        ),
        "sources": [],
        "patch": patch,
        "apply_result": applied,
        "execution_proof": {
            "executed_tools": [
                "project.kb.map",
                "project.code.patch",
                "project.code.apply",
            ],
            "files_changed": len(changes),
            "paths": paths[:30],
            "server_side_tests_run": False,
            "test_note": (
                "No arbitrary server-side test command was executed by V68. "
                "Work Mode does not claim tests passed unless a real test runner reports it."
            ),
        },
    }


async def _run_calculator_job(job: WorkJob) -> None:
    expression = _extract_expression(job.goal)
    if not expression:
        job.status = "blocked"
        job.stage = "needs-expression"
        job.progress = 100
        job.message = "No safe arithmetic expression found"
        job.result = {
            "answer": "I could not extract a safe arithmetic expression from this Work request.",
            "sources": [],
            "execution_proof": {"executed_tools": []},
        }
        return

    result = safe_calculate(expression)
    _event(
        job,
        step="calculate",
        state="completed",
        detail=f"Calculated expression: {expression}",
        tool="calculator.run",
        evidence={"expression": expression, "result": result},
    )
    job.status = "succeeded"
    job.stage = "ready"
    job.progress = 100
    job.message = "Calculation completed"
    job.result = {
        "answer": f"{expression} = {result}",
        "sources": [],
        "execution_proof": {
            "executed_tools": ["calculator.run"],
            "expression": expression,
            "result": result,
        },
    }


async def _run_direct_job(job: WorkJob, settings: Any) -> None:
    await _set_progress(
        job,
        stage="producing-deliverable",
        progress=45,
        message="Producing the requested deliverable",
    )
    prompt = f"""You are Vasuki Work Mode V68.

GOAL:
{job.goal}

Rules:
- Produce the finished requested deliverable, not a discussion about how you might do it.
- Never claim that you browsed, changed files, ran tests, sent messages, deployed,
  or used any external tool unless execution evidence explicitly exists.
- If the goal requires an unavailable external action, clearly state what was not executed.
- Be concise but complete.
"""
    answer, provider = await route_chat_v10(
        "auto",
        [{"role": "user", "content": prompt}],
        settings,
        "",
        require_current=False,
    )
    _event(
        job,
        step="deliverable",
        state="completed",
        detail="Generated a non-tool deliverable with execution-claim restrictions.",
        tool="llm.deliverable",
        evidence={"provider": provider},
    )
    job.status = "succeeded"
    job.stage = "ready"
    job.progress = 100
    job.message = "Work deliverable completed"
    job.result = {
        "answer": str(answer or "").strip(),
        "provider": provider,
        "sources": [],
        "execution_proof": {
            "executed_tools": ["llm.deliverable"],
            "external_actions_executed": False,
        },
    }


async def _execute(job: WorkJob, settings: Any) -> None:
    try:
        async with _LOCK:
            current = _JOBS.get(job.id)
            if current:
                current.status = "running"
                current.stage = "planning"
                current.progress = 8
                current.message = "Planning the work"
                current.updated_at = time.time()

        contract = work_contract(job.goal, project_id=job.project_id)
        job.plan = contract["plan"]
        _event(
            job,
            step="plan",
            state="completed",
            detail=f"Work plan created for mode={contract['mode']}.",
            tool="planner",
            evidence={"support": contract["support"]},
        )

        mode = contract["mode"]
        if mode == "research":
            await _run_research_job(job, settings)
        elif mode == "code_agent":
            await _run_project_code_job(job, settings)
        elif mode == "calculator":
            await _run_calculator_job(job)
        elif mode in {"image", "artifact"}:
            job.status = "blocked"
            job.stage = "use-specialized-workflow"
            job.progress = 100
            job.message = "Use Vasuki's specialized image/artifact workflow for this task"
            job.result = {
                "answer": (
                    "This task was not executed inside V68 Work Mode because Vasuki already has "
                    "a specialized workflow for it. No fake execution was recorded."
                ),
                "sources": [],
                "execution_proof": {
                    "executed_tools": [],
                    "blocked_reason": f"specialized-{mode}-workflow",
                },
            }
        else:
            await _run_direct_job(job, settings)

    except asyncio.CancelledError:
        job.status = "cancelled"
        job.stage = "cancelled"
        job.progress = 100
        job.message = "Work cancelled"
        if job.result is None:
            job.result = {
                "answer": "Work was cancelled before completion.",
                "sources": [],
                "execution_proof": {"cancelled": True},
            }
        raise
    except Exception as exc:
        failed_stage = job.stage
        job.status = "failed"
        job.stage = "failed"
        job.progress = 100
        job.error = f"{type(exc).__name__}: {str(exc)[:1800]}"
        job.message = f"Work failed during {failed_stage}: {str(exc)[:500]}"
        job.result = {
            "answer": "Work failed before completion. No unverified completion claim was made.",
            "sources": [],
            "execution_proof": {
                "failed": True,
                "error_type": type(exc).__name__,
            },
        }
        _event(
            job,
            step="runtime",
            state="failed",
            detail=str(exc)[:800],
        )
    finally:
        job.updated_at = time.time()


async def _cleanup(ttl_seconds: int = 3600) -> None:
    cutoff = time.time() - max(300, int(ttl_seconds))
    async with _LOCK:
        stale = [
            job_id
            for job_id, job in _JOBS.items()
            if job.updated_at < cutoff and job.status in TERMINAL_STATES
        ]
        for job_id in stale:
            _JOBS.pop(job_id, None)


async def create_work_job(
    settings: Any,
    *,
    user_id: str,
    goal: str,
    project_id: str | None = None,
    ttl_seconds: int = 3600,
) -> dict[str, Any]:
    await _cleanup(ttl_seconds)

    value = str(goal or "").strip()
    if len(value) < 3:
        raise ValueError("Work goal is too short.")

    job = WorkJob(
        id=uuid.uuid4().hex,
        user_id=user_id,
        goal=value[:20000],
        project_id=str(project_id or "").strip() or None,
    )

    async with _LOCK:
        active = sum(
            1
            for item in _JOBS.values()
            if item.user_id == user_id
            and item.status in {"queued", "running", "awaiting_approval"}
        )
        if active >= 2:
            raise RuntimeError("You already have two active Work Mode jobs.")
        _JOBS[job.id] = job

    job.task = asyncio.create_task(
        _execute(job, settings),
        name=f"vasuki-work-{job.id[:8]}",
    )
    return job.snapshot()


async def get_work_job(
    *,
    user_id: str,
    job_id: str,
    ttl_seconds: int = 3600,
) -> dict[str, Any] | None:
    await _cleanup(ttl_seconds)
    async with _LOCK:
        job = _JOBS.get(job_id)
        if not job or job.user_id != user_id:
            return None
        return job.snapshot()


async def approve_work_job(
    *,
    user_id: str,
    job_id: str,
    approve: bool,
) -> dict[str, Any] | None:
    async with _LOCK:
        job = _JOBS.get(job_id)
        if not job or job.user_id != user_id:
            return None
        if job.status != "awaiting_approval":
            return job.snapshot()
        job.approval_decision = "approve" if approve else "reject"
        job.updated_at = time.time()
        job.approval_event.set()
        return job.snapshot()


async def cancel_work_job(
    *,
    user_id: str,
    job_id: str,
) -> dict[str, Any] | None:
    async with _LOCK:
        job = _JOBS.get(job_id)
        if not job or job.user_id != user_id:
            return None
        if job.status in TERMINAL_STATES:
            return job.snapshot()
        job.approval_decision = "reject"
        job.approval_event.set()
        task = job.task

    if task and not task.done():
        task.cancel()

    async with _LOCK:
        current = _JOBS.get(job_id)
        return current.snapshot() if current else None


async def shutdown_work_jobs() -> None:
    async with _LOCK:
        tasks = [
            job.task
            for job in _JOBS.values()
            if job.task and not job.task.done()
        ]
    for task in tasks:
        task.cancel()


def health_snapshot() -> dict[str, Any]:
    states: dict[str, int] = {}
    for job in list(_JOBS.values()):
        states[job.status] = states.get(job.status, 0) + 1

    return {
        "ok": True,
        "version": "v68",
        "name": "Vasuki Real Work Mode",
        "features": [
            "goal-to-execution-plan",
            "real-live-research-jobs",
            "real-project-codebase-inspection",
            "real-project-patch-generation",
            "explicit-approval-before-project-write",
            "real-project-file-apply",
            "deterministic-calculator",
            "execution-proof-events",
            "no-fake-test-claims",
            "cancel-work",
        ],
        "job_engine": {
            "type": "in-process-async",
            "states": states,
            "per_user_active_limit": 2,
            "result_ttl_seconds": 3600,
            "restart_persistence": False,
        },
        "safety": {
            "project_writes_require_explicit_approval": True,
            "server_side_arbitrary_test_execution": False,
            "fake_execution_claims_allowed": False,
        },
        "new_database_migration_required": False,
    }
