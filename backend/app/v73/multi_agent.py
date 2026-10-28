from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.services.chat_v10 import route_chat_v10
from app.v11.research import run_research
from app.v13.autonomy import build_execution_plan
from app.v13.critic import critic_review


TERMINAL_STATES = {"succeeded", "failed", "cancelled", "blocked"}


@dataclass
class MultiAgentJob:
    id: str
    user_id: str
    goal: str
    project_id: str | None = None
    status: str = "queued"
    stage: str = "queued"
    progress: int = 0
    message: str = "Multi-agent work queued"
    error: str = ""
    plan: dict[str, Any] | None = None
    agent_status: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    task: asyncio.Task | None = None

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
            "agent_status": list(self.agent_status),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.status in TERMINAL_STATES and self.result is not None:
            payload["result"] = self.result
        return payload


_JOBS: dict[str, MultiAgentJob] = {}
_LOCK = asyncio.Lock()


def _bounded_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def _bounded_float(value: Any, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def health_snapshot(settings: Any | None = None) -> dict[str, Any]:
    max_agents = _bounded_int(
        getattr(settings, "v73_max_agents", 3) if settings is not None else 3,
        3,
        2,
        4,
    )
    parallel = _bounded_int(
        getattr(settings, "v73_max_parallel_agents", 3) if settings is not None else 3,
        3,
        1,
        max_agents,
    )
    timeout = _bounded_float(
        getattr(settings, "v73_agent_timeout_seconds", 35.0) if settings is not None else 35.0,
        35.0,
        8.0,
        90.0,
    )
    return {
        "ok": True,
        "version": "v73",
        "name": "Vasuki Multi-Agent Brain",
        "features": [
            "deterministic-execution-plan",
            "parallel-specialist-agents",
            "optional-live-research-agent",
            "project-brain-context",
            "synthesis-agent",
            "deterministic-critic-gate",
            "single-repair-pass",
            "async-job-progress",
            "cancellation",
            "execution-proof",
        ],
        "roles": ["planner", "specialist", "researcher", "synthesizer", "critic"],
        "cost_controls": {
            "max_specialist_agents": max_agents,
            "max_parallel_agents": parallel,
            "per_agent_timeout_seconds": timeout,
            "max_repair_passes": 1,
            "one_active_job_per_user": True,
        },
        "safety": {
            "external_writes": False,
            "destructive_actions": False,
            "fake_tool_execution_claims": False,
            "project_context_read_only": True,
        },
        "persistence": {"jobs": "in-memory", "survives_restart": False},
        "new_database_migration_required": False,
        "new_api_key_required": False,
    }


def _roles_for_mode(mode: str, max_agents: int) -> list[str]:
    mapping = {
        "research": ["source_analyst", "skeptic", "strategist", "fact_reviewer"],
        "code_agent": ["architect", "coder", "qa_reviewer", "risk_reviewer"],
        "image": ["designer", "requirements_reviewer", "brand_reviewer", "strategist"],
        "artifact": ["document_architect", "requirements_reviewer", "editor", "strategist"],
        "calculator": ["quant_analyst", "checker", "explainer", "skeptic"],
    }
    return mapping.get(
        mode,
        ["solver", "skeptic", "strategist", "requirements_reviewer"],
    )[:max_agents]


def _role_instruction(role: str) -> str:
    instructions = {
        "source_analyst": "Focus on evidence quality, source conflicts, freshness, and what can actually be supported.",
        "skeptic": "Challenge assumptions, missing constraints, counterexamples, and overconfident claims.",
        "strategist": "Focus on practical sequencing, tradeoffs, leverage, and the best next action.",
        "fact_reviewer": "Focus on factual consistency and flag anything needing verification.",
        "architect": "Map technical design, interfaces, dependencies, and the minimal safe implementation path.",
        "coder": "Propose concrete implementation details without claiming code was executed.",
        "qa_reviewer": "Find regression risks, edge cases, tests, and failure modes.",
        "risk_reviewer": "Identify security, privacy, reliability, compatibility, and rollout risks.",
        "designer": "Focus on UX, visual hierarchy, interaction design, and usability constraints.",
        "requirements_reviewer": "Check every explicit user constraint and identify anything easy to miss.",
        "brand_reviewer": "Focus on consistency, messaging, visual identity, and audience fit.",
        "document_architect": "Design structure, information hierarchy, and completeness.",
        "editor": "Improve clarity, precision, concision, and consistency while preserving intent.",
        "quant_analyst": "Reason quantitatively and make assumptions explicit.",
        "checker": "Independently verify calculations and logical steps.",
        "explainer": "Turn the solution into a clear, practical explanation without losing precision.",
        "solver": "Produce the strongest direct solution to the user's objective.",
    }
    return instructions.get(role, "Solve the task from your specialist perspective.")


def _compact_project_context(snapshot: dict[str, Any] | None) -> str:
    if not isinstance(snapshot, dict):
        return ""
    project = snapshot.get("project") if isinstance(snapshot.get("project"), dict) else {}
    goal = snapshot.get("goal") if isinstance(snapshot.get("goal"), dict) else {}
    last_work = snapshot.get("last_work") if isinstance(snapshot.get("last_work"), dict) else {}
    tasks = snapshot.get("tasks") if isinstance(snapshot.get("tasks"), list) else []
    decisions = snapshot.get("decisions") if isinstance(snapshot.get("decisions"), list) else []
    files = snapshot.get("files") if isinstance(snapshot.get("files"), dict) else {}
    compact = {
        "project": {
            "id": project.get("id"),
            "name": project.get("name"),
            "description": project.get("description"),
        },
        "goal": goal,
        "last_work": last_work,
        "open_tasks": [
            item
            for item in tasks
            if isinstance(item, dict) and str(item.get("status") or "") != "done"
        ][:12],
        "recent_decisions": [item for item in decisions if isinstance(item, dict)][-8:],
        "files": {"count": files.get("count"), "languages": files.get("languages")},
    }
    return json.dumps(compact, ensure_ascii=False, default=str)[:18000]


async def _project_context(
    settings: Any,
    *,
    user_id: str,
    project_id: str | None,
) -> str:
    if not project_id:
        return ""
    try:
        from app.v71.project_brain import project_brain_snapshot

        snapshot = await asyncio.wait_for(
            project_brain_snapshot(
                settings,
                user_id=user_id,
                project_id=project_id,
            ),
            timeout=8.0,
        )
        return _compact_project_context(snapshot)
    except Exception:
        return ""


async def _set_progress(
    job: MultiAgentJob,
    *,
    stage: str,
    progress: int,
    message: str,
) -> None:
    async with _LOCK:
        current = _JOBS.get(job.id)
        if current is None:
            return
        if current.status == "queued":
            current.status = "running"
        current.stage = stage[:80]
        current.progress = max(0, min(100, int(progress)))
        current.message = message[:500]
        current.updated_at = time.time()


async def _set_agent_status(
    job: MultiAgentJob,
    *,
    role: str,
    status: str,
    provider: str = "",
    error: str = "",
) -> None:
    async with _LOCK:
        current = _JOBS.get(job.id)
        if current is None:
            return
        for item in current.agent_status:
            if item.get("role") == role:
                item.update(
                    {
                        "status": status,
                        "provider": provider or item.get("provider") or "",
                        "error": error[:500] if error else None,
                    }
                )
                break
        else:
            current.agent_status.append(
                {
                    "role": role,
                    "status": status,
                    "provider": provider,
                    "error": error[:500] if error else None,
                }
            )
        current.updated_at = time.time()


async def _model_specialist(
    settings: Any,
    *,
    role: str,
    goal: str,
    plan: dict[str, Any],
    project_context: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    system = (
        "You are one specialist inside Vasuki Multi-Agent Brain. "
        "Do not pretend to have executed tools, code, browser actions, writes, tests, or external actions. "
        "Return concise, decision-useful analysis for the synthesizer. "
        + _role_instruction(role)
    )
    user = f"""OBJECTIVE:
{goal}

EXECUTION PLAN:
{json.dumps(plan, ensure_ascii=False, default=str)[:16000]}

PROJECT CONTEXT (read-only; may be empty):
{project_context or "(none)"}

Give:
1. key findings,
2. recommended approach,
3. risks/unknowns,
4. exact points the final synthesizer must preserve.
"""
    answer, provider = await asyncio.wait_for(
        route_chat_v10(
            "auto",
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            settings,
            project_context[:12000],
        ),
        timeout=timeout_seconds,
    )
    return {"role": role, "answer": answer[:24000], "provider": provider}


async def _live_research(
    settings: Any,
    *,
    goal: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        report = await asyncio.wait_for(
            run_research(goal, settings),
            timeout=max(20.0, min(90.0, timeout_seconds * 1.7)),
        )
    except Exception as exc:
        return {
            "ok": False,
            "answer": "",
            "sources": [],
            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
        }
    sources = report.get("sources") if isinstance(report, dict) else []
    return {
        "ok": bool(sources),
        "answer": str(report.get("answer") or "")[:32000] if isinstance(report, dict) else "",
        "sources": sources if isinstance(sources, list) else [],
        "error": "",
    }


async def _synthesize(
    settings: Any,
    *,
    goal: str,
    plan: dict[str, Any],
    specialists: list[dict[str, Any]],
    research: dict[str, Any],
    project_context: str,
    timeout_seconds: float,
) -> tuple[str, str]:
    evidence = {
        "specialists": specialists,
        "live_research": {
            "answer": research.get("answer"),
            "sources": research.get("sources"),
            "error": research.get("error"),
        },
    }
    prompt = f"""You are the synthesizer for Vasuki Multi-Agent Brain.

USER OBJECTIVE:
{goal}

PLAN:
{json.dumps(plan, ensure_ascii=False, default=str)[:16000]}

READ-ONLY PROJECT CONTEXT:
{project_context or "(none)"}

AGENT EVIDENCE:
{json.dumps(evidence, ensure_ascii=False, default=str)[:70000]}

Produce one final answer that:
- directly solves the user's objective,
- resolves disagreements between specialists,
- uses live-research facts only when supported by supplied sources,
- distinguishes verified facts from recommendations,
- does not claim external writes, tests, browser actions, deployments, or code execution not present in evidence,
- is concise but complete.
"""
    return await asyncio.wait_for(
        route_chat_v10(
            "auto",
            [{"role": "user", "content": prompt}],
            settings,
            json.dumps(evidence, ensure_ascii=False, default=str)[:60000],
            require_current=bool(research.get("sources")),
        ),
        timeout=timeout_seconds,
    )


async def _repair(
    settings: Any,
    *,
    goal: str,
    answer: str,
    instruction: str,
    specialists: list[dict[str, Any]],
    research: dict[str, Any],
    timeout_seconds: float,
) -> tuple[str, str]:
    prompt = f"""Repair this multi-agent answer.

USER OBJECTIVE:
{goal}

CRITIC INSTRUCTION:
{instruction}

CURRENT ANSWER:
{answer}

SPECIALIST EVIDENCE:
{json.dumps(specialists, ensure_ascii=False, default=str)[:45000]}

LIVE RESEARCH:
{json.dumps(research, ensure_ascii=False, default=str)[:30000]}

Return only the corrected final answer. Do not add unsupported claims.
"""
    return await asyncio.wait_for(
        route_chat_v10(
            "auto",
            [{"role": "user", "content": prompt}],
            settings,
            json.dumps(research, ensure_ascii=False, default=str)[:24000],
            require_current=bool(research.get("sources")),
        ),
        timeout=timeout_seconds,
    )


async def _execute(job: MultiAgentJob, settings: Any) -> None:
    started = time.perf_counter()
    max_agents = _bounded_int(getattr(settings, "v73_max_agents", 3), 3, 2, 4)
    max_parallel = _bounded_int(
        getattr(settings, "v73_max_parallel_agents", 3),
        3,
        1,
        max_agents,
    )
    timeout_seconds = _bounded_float(
        getattr(settings, "v73_agent_timeout_seconds", 35.0),
        35.0,
        8.0,
        90.0,
    )

    try:
        await _set_progress(
            job,
            stage="planning",
            progress=8,
            message="Building multi-agent execution plan",
        )
        plan_obj = build_execution_plan(
            [{"role": "user", "content": job.goal}],
            require_current=False,
        )
        plan = plan_obj.to_dict()
        job.plan = plan
        mode = str(plan.get("mode") or "chat")
        roles = _roles_for_mode(mode, max_agents)

        project_context = await _project_context(
            settings,
            user_id=job.user_id,
            project_id=job.project_id,
        )

        await _set_progress(
            job,
            stage="parallel-agents",
            progress=20,
            message=f"Running {len(roles)} specialist agents",
        )
        semaphore = asyncio.Semaphore(max_parallel)

        async def run_role(role: str) -> dict[str, Any]:
            await _set_agent_status(job, role=role, status="running")
            try:
                async with semaphore:
                    result = await _model_specialist(
                        settings,
                        role=role,
                        goal=job.goal,
                        plan=plan,
                        project_context=project_context,
                        timeout_seconds=timeout_seconds,
                    )
                await _set_agent_status(
                    job,
                    role=role,
                    status="completed",
                    provider=str(result.get("provider") or ""),
                )
                return result
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error = f"{type(exc).__name__}: {str(exc)[:500]}"
                await _set_agent_status(
                    job,
                    role=role,
                    status="failed",
                    error=error,
                )
                return {"role": role, "answer": "", "provider": "", "error": error}

        specialist_tasks = [asyncio.create_task(run_role(role)) for role in roles]
        research_task = (
            asyncio.create_task(
                _live_research(
                    settings,
                    goal=job.goal,
                    timeout_seconds=timeout_seconds,
                )
            )
            if mode == "research"
            else None
        )

        specialists = await asyncio.gather(*specialist_tasks)
        usable = [
            item
            for item in specialists
            if isinstance(item, dict) and str(item.get("answer") or "").strip()
        ]

        research = {"ok": False, "answer": "", "sources": [], "error": ""}
        if research_task is not None:
            await _set_agent_status(job, role="researcher", status="running")
            try:
                research = await research_task
                await _set_agent_status(
                    job,
                    role="researcher",
                    status="completed" if research.get("ok") else "blocked",
                    error=str(research.get("error") or ""),
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                research = {
                    "ok": False,
                    "answer": "",
                    "sources": [],
                    "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                }
                await _set_agent_status(
                    job,
                    role="researcher",
                    status="failed",
                    error=research["error"],
                )

        if not usable and not research.get("answer"):
            raise RuntimeError("All V73 specialist agents failed before synthesis.")

        await _set_progress(
            job,
            stage="synthesizing",
            progress=68,
            message="Synthesizing specialist outputs",
        )
        answer, synth_provider = await _synthesize(
            settings,
            goal=job.goal,
            plan=plan,
            specialists=usable,
            research=research,
            project_context=project_context,
            timeout_seconds=timeout_seconds,
        )
        await _set_agent_status(
            job,
            role="synthesizer",
            status="completed",
            provider=synth_provider,
        )

        sources = research.get("sources") if isinstance(research.get("sources"), list) else []
        critic = critic_review(
            job.goal,
            answer,
            sources=sources,
            current_required=mode == "research",
        )
        await _set_agent_status(job, role="critic", status="completed")

        repair_used = False
        repair_provider = ""
        if critic.needs_repair:
            await _set_progress(
                job,
                stage="repairing",
                progress=84,
                message="Critic requested one bounded repair pass",
            )
            try:
                repaired, repair_provider = await _repair(
                    settings,
                    goal=job.goal,
                    answer=answer,
                    instruction=critic.repair_instruction,
                    specialists=usable,
                    research=research,
                    timeout_seconds=timeout_seconds,
                )
                if repaired.strip():
                    answer = repaired.strip()
                    repair_used = True
                    critic = critic_review(
                        job.goal,
                        answer,
                        sources=sources,
                        current_required=mode == "research",
                    )
            except Exception:
                pass

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        job.status = "succeeded"
        job.stage = "ready"
        job.progress = 100
        job.message = "Multi-agent synthesis completed"
        job.result = {
            "answer": answer,
            "provider": synth_provider,
            "sources": sources,
            "mode": mode,
            "agent_outputs": usable,
            "critic": critic.to_dict(),
            "execution_proof": {
                "engine": "vasuki-v73-multi-agent",
                "specialist_agents_requested": len(roles),
                "specialist_agents_completed": len(usable),
                "agent_roles": roles,
                "parallel_limit": max_parallel,
                "live_research_used": research_task is not None,
                "live_research_source_count": len(sources),
                "synthesis_provider": synth_provider,
                "repair_pass_used": repair_used,
                "repair_provider": repair_provider,
                "external_writes": 0,
                "destructive_actions": 0,
                "project_context_read_only": bool(project_context),
                "duration_ms": elapsed_ms,
            },
        }
        job.updated_at = time.time()

    except asyncio.CancelledError:
        job.status = "cancelled"
        job.stage = "cancelled"
        job.progress = 100
        job.message = "Multi-agent work cancelled"
        job.updated_at = time.time()
        raise
    except Exception as exc:
        job.status = "failed"
        job.stage = "failed"
        job.progress = 100
        job.error = f"{type(exc).__name__}: {str(exc)[:900]}"
        job.message = "Multi-agent work failed"
        job.updated_at = time.time()


async def create_multi_agent_job(
    settings: Any,
    *,
    user_id: str,
    goal: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    objective = str(goal or "").strip()
    if len(objective) < 3:
        raise ValueError("Multi-agent goal is too short.")

    async with _LOCK:
        for existing in _JOBS.values():
            if existing.user_id == user_id and existing.status not in TERMINAL_STATES:
                raise RuntimeError("A V73 multi-agent job is already active for this user.")
        job = MultiAgentJob(
            id=uuid.uuid4().hex,
            user_id=user_id,
            goal=objective[:20000],
            project_id=project_id,
        )
        _JOBS[job.id] = job
        job.task = asyncio.create_task(_execute(job, settings))
        return job.snapshot()


async def get_multi_agent_job(
    *,
    user_id: str,
    job_id: str,
) -> dict[str, Any] | None:
    async with _LOCK:
        job = _JOBS.get(job_id)
        if job is None or job.user_id != user_id:
            return None
        return job.snapshot()


async def cancel_multi_agent_job(
    *,
    user_id: str,
    job_id: str,
) -> dict[str, Any] | None:
    async with _LOCK:
        job = _JOBS.get(job_id)
        if job is None or job.user_id != user_id:
            return None
        task = job.task
        if job.status not in TERMINAL_STATES:
            job.status = "cancelled"
            job.stage = "cancelled"
            job.progress = 100
            job.message = "Multi-agent work cancelled"
            job.updated_at = time.time()
    if task is not None and not task.done():
        task.cancel()
    return await get_multi_agent_job(user_id=user_id, job_id=job_id)


async def shutdown_multi_agent_jobs() -> None:
    async with _LOCK:
        tasks = [
            job.task
            for job in _JOBS.values()
            if job.task is not None and not job.task.done()
        ]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
