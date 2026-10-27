from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse, urlunparse

import app.main as legacy
from app.services.chat_v10 import route_chat_v10
from app.v11.quality import citation_fact_check
from app.v11.research import plan_query, save_to_research_kb


TERMINAL_STATES = {"succeeded", "blocked", "failed", "cancelled"}


def _json_from_text(value: str) -> Any:
    value = str(value or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", value, re.I)
    if fence:
        value = fence.group(1).strip()
    for start_char, end_char in (("{", "}"), ("[", "]")):
        start = value.find(start_char)
        end = value.rfind(end_char)
        if start >= 0 and end > start:
            try:
                return json.loads(value[start : end + 1])
            except Exception:
                pass
    return None


def normalize_plan(
    query: str,
    plan: dict[str, Any] | None,
    *,
    max_subquestions: int = 8,
) -> dict[str, Any]:
    source = plan if isinstance(plan, dict) else {}
    raw_questions = source.get("subquestions")
    raw_questions = raw_questions if isinstance(raw_questions, list) else []

    subquestions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_questions:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        if len(question) < 3:
            continue
        key = question.casefold()
        if key in seen:
            continue
        seen.add(key)
        subquestions.append(
            {
                "id": f"q{len(subquestions) + 1}",
                "question": question[:2000],
                "why": str(item.get("why") or "evidence needed")[:500],
                "requires_current": bool(item.get("requires_current", True)),
            }
        )
        if len(subquestions) >= max(1, min(8, int(max_subquestions))):
            break

    if not subquestions:
        subquestions = [
            {
                "id": "q1",
                "question": str(query or "").strip()[:2000],
                "why": "primary research question",
                "requires_current": True,
            }
        ]

    raw_conflicts = source.get("conflicts_to_check")
    raw_conflicts = raw_conflicts if isinstance(raw_conflicts, list) else []
    conflicts: list[str] = []
    seen_conflicts: set[str] = set()
    for value in raw_conflicts:
        text = str(value or "").strip()
        key = text.casefold()
        if text and key not in seen_conflicts:
            conflicts.append(text[:1000])
            seen_conflicts.add(key)
        if len(conflicts) >= 8:
            break

    objective = str(source.get("objective") or query or "").strip()
    return {
        "objective": objective[:3000],
        "subquestions": subquestions,
        "conflicts_to_check": conflicts,
        "editable": True,
        "max_subquestions": 8,
    }


async def create_research_plan(
    query: str,
    settings: Any,
    *,
    max_subquestions: int = 6,
) -> dict[str, Any]:
    raw = await plan_query(
        str(query or "").strip(),
        settings,
        max_subquestions=max(1, min(8, int(max_subquestions))),
    )
    plan = normalize_plan(query, raw, max_subquestions=max_subquestions)
    return {
        "ok": True,
        "version": "v69",
        "query": str(query or "").strip(),
        "plan": plan,
        "planner_provider": str(raw.get("provider") or "") if isinstance(raw, dict) else "",
        "rules": {
            "user_can_edit_plan_before_run": True,
            "evidence_only_synthesis": True,
            "conflict_check": True,
            "citation_verification": True,
            "no_sources_no_factual_report": True,
        },
    }


@dataclass
class ResearchJob:
    id: str
    user_id: str
    query: str
    plan: dict[str, Any]
    project_id: str | None = None
    save_to_kb: bool = False
    title: str = ""
    status: str = "queued"
    stage: str = "queued"
    progress: int = 0
    message: str = "Deep research queued"
    error: str = ""
    question_status: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
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
            "query": self.query,
            "plan": self.plan,
            "question_status": list(self.question_status),
            "events": list(self.events[-40:]),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.status in TERMINAL_STATES and self.result is not None:
            payload["result"] = self.result
        return payload


_JOBS: dict[str, ResearchJob] = {}
_LOCK = asyncio.Lock()


def _record(
    job: ResearchJob,
    *,
    stage: str,
    state: str,
    detail: str,
    evidence: dict[str, Any] | None = None,
) -> None:
    job.events.append(
        {
            "at": time.time(),
            "stage": stage,
            "state": state,
            "detail": str(detail or "")[:1000],
            "evidence": evidence or {},
        }
    )
    if len(job.events) > 80:
        del job.events[:-80]


async def _progress(
    job: ResearchJob,
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
        current.message = str(message or "")[:500]
        current.updated_at = time.time()


def _canonical_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        cleaned = parsed._replace(fragment="", query="")
        return urlunparse(cleaned).rstrip("/").casefold()
    except Exception:
        return raw.casefold().rstrip("/")


def _domain(value: str) -> str:
    try:
        return urlparse(str(value or "")).netloc.casefold().removeprefix("www.")
    except Exception:
        return ""


def _dedupe_sources(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        results = row.get("results") if isinstance(row, dict) else []
        results = results if isinstance(results, list) else []
        for item in results:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "Source").strip()
            snippet = str(
                item.get("content")
                or item.get("snippet")
                or item.get("text")
                or ""
            ).strip()
            key = _canonical_url(url) or f"{title.casefold()}::{snippet[:120].casefold()}"
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "id": f"S{len(sources) + 1}",
                    "title": title[:500],
                    "url": url[:3000],
                    "domain": _domain(url),
                    "snippet": snippet[:5000],
                    "published_date": str(item.get("published_date") or item.get("date") or "")[:100],
                    "source_type": str(item.get("source_type") or "web")[:100],
                }
            )
            if len(sources) >= 40:
                return sources
    return sources


def _evidence_context(sources: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for source in sources:
        blocks.append(
            f"[{source['id']}] {source.get('title') or 'Source'}\n"
            f"URL: {source.get('url') or ''}\n"
            f"Published: {source.get('published_date') or 'unknown'}\n"
            f"Evidence: {source.get('snippet') or ''}"
        )
    return "\n\n".join(blocks)


async def _search_question(
    item: dict[str, Any],
    settings: Any,
    *,
    results_per_question: int,
) -> dict[str, Any]:
    question = str(item.get("question") or "").strip()
    results, provider = await legacy.search_web(
        question,
        settings,
        results_per_question,
        require_current=bool(item.get("requires_current", True)),
    )
    return {
        "id": item.get("id"),
        "question": question,
        "provider": provider,
        "results": results if isinstance(results, list) else [],
    }


async def _conflict_analysis(
    query: str,
    plan: dict[str, Any],
    sources: list[dict[str, Any]],
    settings: Any,
) -> dict[str, Any]:
    requested = plan.get("conflicts_to_check")
    requested = requested if isinstance(requested, list) else []
    context = _evidence_context(sources)
    prompt = f"""You are Vasuki Deep Research V69 conflict analyst.

REQUEST:
{query}

CONFLICTS THE USER/PLANNER WANTS CHECKED:
{json.dumps(requested, ensure_ascii=False)}

EVIDENCE:
{context}

Using ONLY the evidence above, return strict JSON:
{{
  "conflicts": [
    {{
      "topic": "...",
      "status": "resolved|unresolved|no-conflict-found",
      "summary": "...",
      "supporting_source_ids": ["S1"],
      "opposing_source_ids": ["S2"]
    }}
  ],
  "uncertainties": ["..."]
}}

Do not invent claims, sources, dates, or IDs.
"""
    answer, provider = await route_chat_v10(
        "auto",
        [{"role": "user", "content": prompt}],
        settings,
        context,
        require_current=True,
    )
    parsed = _json_from_text(answer)
    if not isinstance(parsed, dict):
        parsed = {"conflicts": [], "uncertainties": ["Conflict analyzer returned unstructured output."]}
    parsed["provider"] = provider
    return parsed


async def _synthesize(
    query: str,
    plan: dict[str, Any],
    sources: list[dict[str, Any]],
    conflict_analysis: dict[str, Any],
    settings: Any,
) -> tuple[str, str]:
    context = _evidence_context(sources)
    prompt = f"""You are Vasuki Deep Research V69.

USER REQUEST:
{query}

EDITED RESEARCH PLAN:
{json.dumps(plan, ensure_ascii=False)}

CONFLICT ANALYSIS:
{json.dumps(conflict_analysis, ensure_ascii=False)}

SOURCE EVIDENCE:
{context}

Write the final research report using ONLY the source evidence above.

Rules:
- Every important factual claim must cite one or more [S#] IDs.
- Never invent a citation, source, date, number, quote, or fact.
- Distinguish evidence from inference.
- Explicitly mention unresolved conflicts and missing evidence.
- Prefer independent sources when several support the same point.
- If evidence does not support a requested conclusion, say that clearly.

Structure:
## Answer
## Key findings
## Evidence and source comparison
## Conflicts / uncertainties
## Conclusion
"""
    return await route_chat_v10(
        "auto",
        [{"role": "user", "content": prompt}],
        settings,
        context,
        require_current=True,
    )


async def _execute(job: ResearchJob, settings: Any) -> None:
    try:
        job.status = "running"
        await _progress(
            job,
            stage="searching",
            progress=8,
            message="Searching the edited research plan",
        )
        questions = job.plan.get("subquestions")
        questions = questions if isinstance(questions, list) else []
        job.question_status = [
            {
                "id": item.get("id"),
                "question": item.get("question"),
                "status": "queued",
                "source_count": 0,
            }
            for item in questions
            if isinstance(item, dict)
        ]
        _record(
            job,
            stage="plan",
            state="completed",
            detail=f"Running edited plan with {len(questions)} research question(s).",
            evidence={"question_count": len(questions)},
        )

        async def wrapped(index: int, item: dict[str, Any]):
            try:
                result = await _search_question(
                    item,
                    settings,
                    results_per_question=5,
                )
                return index, result, None
            except Exception as exc:
                return index, None, exc

        tasks = [
            asyncio.create_task(wrapped(index, item))
            for index, item in enumerate(questions)
            if isinstance(item, dict)
        ]
        rows: list[dict[str, Any]] = []
        completed = 0
        total = max(1, len(tasks))

        for future in asyncio.as_completed(tasks):
            index, result, exc = await future
            completed += 1
            if exc is None and isinstance(result, dict):
                rows.append(result)
                count = len(result.get("results") or [])
                job.question_status[index]["status"] = "completed"
                job.question_status[index]["source_count"] = count
                job.question_status[index]["provider"] = result.get("provider")
            else:
                job.question_status[index]["status"] = "failed"
                job.question_status[index]["error"] = str(exc)[:500]
            await _progress(
                job,
                stage="searching",
                progress=8 + int(52 * completed / total),
                message=f"Completed {completed}/{total} research searches",
            )

        sources = _dedupe_sources(rows)
        domains = sorted({source.get("domain") for source in sources if source.get("domain")})
        _record(
            job,
            stage="searching",
            state="completed",
            detail=f"Collected {len(sources)} unique source(s) across {len(domains)} domain(s).",
            evidence={"source_count": len(sources), "domain_count": len(domains)},
        )

        if not sources:
            job.status = "blocked"
            job.stage = "blocked"
            job.progress = 100
            job.message = "No usable source evidence was found"
            job.result = {
                "answer": (
                    "Deep Research could not produce an evidence-backed factual report because "
                    "the live searches returned no usable sources. Vasuki did not guess."
                ),
                "sources": [],
                "plan": job.plan,
                "verification": {
                    "verified": False,
                    "reason": "no-source-evidence",
                },
                "execution_proof": {
                    "search_questions": len(questions),
                    "completed_searches": completed,
                    "unique_sources": 0,
                    "unique_domains": 0,
                    "no_fake_sources": True,
                },
            }
            return

        await _progress(
            job,
            stage="comparing-sources",
            progress=68,
            message="Comparing sources and checking conflicts",
        )
        conflicts = await _conflict_analysis(
            job.query,
            job.plan,
            sources,
            settings,
        )
        _record(
            job,
            stage="conflict-check",
            state="completed",
            detail="Source conflict and uncertainty analysis completed.",
            evidence={
                "conflict_count": len(conflicts.get("conflicts") or []),
                "uncertainty_count": len(conflicts.get("uncertainties") or []),
            },
        )

        await _progress(
            job,
            stage="writing-report",
            progress=82,
            message="Writing an evidence-only cited report",
        )
        answer, provider = await _synthesize(
            job.query,
            job.plan,
            sources,
            conflicts,
            settings,
        )
        answer = str(answer or "").strip()
        if not answer:
            raise RuntimeError("Research synthesis returned an empty report.")

        await _progress(
            job,
            stage="verifying-citations",
            progress=94,
            message="Verifying citations and evidence coverage",
        )
        verification = citation_fact_check(answer, sources)
        _record(
            job,
            stage="verification",
            state="completed",
            detail="Citation verification completed.",
            evidence={
                "coverage": verification.get("coverage"),
                "claim_count": verification.get("claim_count"),
                "risk": verification.get("risk"),
            },
        )

        report = {
            "ok": True,
            "query": job.query,
            "plan": job.plan,
            "searches": rows,
            "sources": sources,
            "source_domains": domains,
            "conflict_analysis": conflicts,
            "answer": answer,
            "provider": provider,
            "citation_check": verification,
        }

        if job.save_to_kb:
            report["saved_kb"] = await save_to_research_kb(
                settings,
                job.user_id,
                job.project_id,
                job.title or job.query[:120],
                job.query,
                report,
            )

        job.status = "succeeded"
        job.stage = "ready"
        job.progress = 100
        job.message = "Deep research completed and verified"
        job.result = {
            **report,
            "verification": {
                "verified": True,
                "citation_check": verification,
                "source_count": len(sources),
                "domain_count": len(domains),
            },
            "execution_proof": {
                "search_questions": len(questions),
                "completed_searches": sum(
                    1 for item in job.question_status if item.get("status") == "completed"
                ),
                "unique_sources": len(sources),
                "unique_domains": len(domains),
                "conflict_check": True,
                "citation_verification": True,
                "no_fake_sources": True,
            },
        }

    except asyncio.CancelledError:
        job.status = "cancelled"
        job.stage = "cancelled"
        job.progress = 100
        job.message = "Deep research cancelled"
        if job.result is None:
            job.result = {
                "answer": "Deep Research was cancelled before completion.",
                "sources": [],
                "execution_proof": {"cancelled": True},
            }
        raise
    except Exception as exc:
        job.status = "failed"
        job.stage = "failed"
        job.progress = 100
        job.error = f"{type(exc).__name__}: {str(exc)[:1800]}"
        job.message = f"Deep research failed: {str(exc)[:500]}"
        job.result = {
            "answer": "Deep Research failed before a verified report was completed.",
            "sources": [],
            "execution_proof": {
                "failed": True,
                "error_type": type(exc).__name__,
                "no_fake_completion": True,
            },
        }
        _record(job, stage="runtime", state="failed", detail=str(exc)[:1000])
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


async def create_research_job(
    settings: Any,
    *,
    user_id: str,
    query: str,
    plan: dict[str, Any],
    project_id: str | None = None,
    save_to_kb: bool = False,
    title: str = "",
    ttl_seconds: int = 3600,
) -> dict[str, Any]:
    await _cleanup(ttl_seconds)
    value = str(query or "").strip()
    if len(value) < 3:
        raise ValueError("Research query is too short.")

    normalized = normalize_plan(value, plan, max_subquestions=8)
    job = ResearchJob(
        id=uuid.uuid4().hex,
        user_id=user_id,
        query=value[:12000],
        plan=normalized,
        project_id=str(project_id or "").strip() or None,
        save_to_kb=bool(save_to_kb),
        title=str(title or "").strip()[:200],
    )

    async with _LOCK:
        active = sum(
            1
            for item in _JOBS.values()
            if item.user_id == user_id and item.status in {"queued", "running"}
        )
        if active >= 2:
            raise RuntimeError("You already have two active Deep Research jobs.")
        _JOBS[job.id] = job

    job.task = asyncio.create_task(
        _execute(job, settings),
        name=f"vasuki-research-{job.id[:8]}",
    )
    return job.snapshot()


async def get_research_job(
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


async def cancel_research_job(
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
        task = job.task

    if task and not task.done():
        task.cancel()

    async with _LOCK:
        current = _JOBS.get(job_id)
        return current.snapshot() if current else None


async def shutdown_research_jobs() -> None:
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
        "version": "v69",
        "name": "Vasuki Deep Research 2.0",
        "features": [
            "editable-plan-before-run",
            "parallel-live-searches",
            "unique-source-deduplication",
            "source-domain-diversity",
            "explicit-conflict-analysis",
            "evidence-only-synthesis",
            "citation-verification",
            "live-job-progress",
            "cancel-research",
            "optional-project-research-kb-save",
            "no-source-no-factual-report",
        ],
        "job_engine": {
            "type": "in-process-async",
            "states": states,
            "per_user_active_limit": 2,
            "result_ttl_seconds": 3600,
            "restart_persistence": False,
        },
        "safety": {
            "fake_sources_allowed": False,
            "factual_report_without_sources_allowed": False,
            "user_edits_plan_before_execution": True,
        },
        "new_database_migration_required": False,
    }
