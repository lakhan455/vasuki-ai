from __future__ import annotations

import asyncio
import io
import json
import time
import zipfile
from typing import Any

from fastapi import Body, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pypdf import PdfReader
from docx import Document

import app.main_v10_omni as v10
import app.services.chat_v7 as chat_v7
from app.auth import AuthUser, get_current_user
from app.services.chat_v10 import route_chat_stream_v10, route_chat_v10
from app.services.router_v7 import classify_route, last_user_query
from app.services.image_v10 import route_image_v10
from app.services.vision import process_vision_request
from app.services.plans_v2 import get_plan_status
from app.v11.agents import TOOLS, consume_permission, grant_once, registry_snapshot, safe_calculate
from app.v11.capabilities import registry as capability_registry
from app.v11.coding import build_knowledge_graph, repair_loop, sandbox_policy
from app.v11.github_agent import compare as github_compare, create_branch as github_create_branch, create_pr as github_create_pr, issue as github_issue, put_file as github_put_file, read_repo_file
from app.v11.media import apply_mask_composite, consistency_prompt, generate_video, multimodal_contract, server_stt, server_tts
from app.v11.memory import active_memory, resolve_conflicts, upsert_temporal_memory
from app.v11.operations import RETENTION_DEFAULTS, abuse_check, db_performance, privacy_snapshot, record_request, release_for_user, rollback, slo_snapshot
from app.v11.quality import citation_fact_check, judge_answer, load_persisted_provider_learning, persist_provider_signal, provider_snapshot, rank_for_task_v11, run_eval
from app.v11.research import run_research, save_to_research_kb
from app.v11.retention import cleanup_v11_tables, policies as retention_policies, set_policy as set_retention_policy
from app.v11.scheduler import create_task, runtime_note, scheduler_tick
from app.v11 import store
from app.v12.api import router as v12_router
from app.v12.memory import resolve_conflicts_v12
from app.v12.provider import provider_snapshot_v12, rank_for_task_v12
from app.v13.verification import verify_answer
from app.v13.analytics import provider_health_summary
from app.v13.autonomy import build_execution_plan
from app.v13.critic import critic_review
from app.v13.deployment import check_deployment
from app.v13.incidents import recovery_plan
from app.v13.orchestrator import orchestrate_request
from app.v13.project_brain import project_snapshot
from app.v14.runtime import prepare_quality_messages, runtime_health
from app.v15.coding_agent import (
    V15_PROJECT_SYSTEM_PROMPT,
    build_project_prompt,
    coder_health,
    extract_zip_text_files,
    merge_existing_files,
    normalize_project_payload,
    package_project_response,
    parse_project_response,
)

app = v10.app
settings = v10.settings

_v11_background_tasks: list[asyncio.Task] = []
_v11_last_rollback_at = 0.0

async def _v11_scheduler_loop():
    while True:
        await asyncio.sleep(max(30, int(getattr(settings, "v11_scheduler_poll_seconds", 60))))
        try:
            await scheduler_tick(settings, _scheduled_executor)
        except Exception:
            pass

async def _v11_release_guard_loop():
    global _v11_last_rollback_at
    while True:
        await asyncio.sleep(60)
        if not bool(getattr(settings, "v11_auto_rollback_enabled", False)):
            continue
        snap=slo_snapshot()
        if int(snap.get("samples") or 0) < int(getattr(settings, "v11_rollback_min_samples", 50)):
            continue
        threshold=float(getattr(settings, "v11_rollback_error_pct", 12.0))
        if float(snap.get("error_pct") or 0) < threshold:
            continue
        now=time.time()
        if now-_v11_last_rollback_at < 1800:
            continue
        try:
            result=await rollback(settings,reason=f"V11 automatic guard: error_pct={snap.get('error_pct')} threshold={threshold}")
            if result.get("triggered"):
                _v11_last_rollback_at=now
        except Exception:
            pass

@app.on_event("startup")
async def v11_startup():
    await load_persisted_provider_learning(settings)
    if bool(getattr(settings, "v11_scheduler_enabled", True)):
        _v11_background_tasks.append(asyncio.create_task(_v11_scheduler_loop()))
    if bool(getattr(settings, "v11_auto_rollback_enabled", False)):
        _v11_background_tasks.append(asyncio.create_task(_v11_release_guard_loop()))

@app.on_event("shutdown")
async def v11_shutdown():
    for task in _v11_background_tasks:
        task.cancel()


# V11 provider quality learning becomes part of Vasuki's existing V7/V10 router.
chat_v7.rank_for_task = rank_for_task_v11
# V12 keeps V11 benchmark learning and adds task-specific runtime
# quality/reliability/speed ranking.
chat_v7.rank_for_task = rank_for_task_v12

async def route_chat_stream_v11(
    provider: str,
    messages: list[dict[str, Any]],
    settings_arg,
    web_context: str = "",
    *,
    require_current: bool = False,
    as_of: str | None = None,
    cache_bypass: bool = False,
    exclude_provider: str | None = None,
):
    messages=prepare_quality_messages(
        messages,
        require_current=require_current,
        web_context=web_context,
    )
    complete=""
    final_provider=""
    async for event in route_chat_stream_v10(
        provider,
        messages,
        settings_arg,
        web_context,
        require_current=require_current,
        as_of=as_of,
        cache_bypass=cache_bypass,
        exclude_provider=exclude_provider,
    ):
        if event.get("type")=="provider":
            final_provider=str(event.get("provider") or "")
        elif event.get("type")=="token":
            complete+=str(event.get("token") or "")
        yield event
    if complete.strip() and final_provider and not final_provider.startswith("cache:"):
        try:
            query=last_user_query(messages)
            task=classify_route(messages,require_current=require_current).task_type
            automatic=judge_answer(query,complete,sources=[])
            verification=verify_answer(
                query,
                complete,
                sources=[],
                current_required=require_current,
            )
            combined_score=min(
                float(automatic["overall"]),
                float(verification.score),
            )
            await persist_provider_signal(
                settings_arg,
                final_provider,
                task,
                "automatic_judge_v13",
                combined_score,
                {
                    "hallucination_risk":max(
                        float(automatic["hallucination_risk"]),
                        float(verification.hallucination_risk),
                    ),
                    "chars":len(complete),
                    "v13_retry_recommended":verification.needs_retry,
                    "v13_issues":list(verification.issues),
                },
            )
        except Exception:
            pass

async def route_chat_v11(
    provider: str,
    messages: list[dict[str, Any]],
    settings_arg,
    web_context: str = "",
    *,
    require_current: bool = False,
    as_of: str | None = None,
):
    answer=""; provider_name=""
    async for event in route_chat_stream_v11(
        provider,messages,settings_arg,web_context,
        require_current=require_current,as_of=as_of,
    ):
        if event.get("type")=="provider": provider_name=str(event.get("provider") or "")
        elif event.get("type")=="token": answer+=str(event.get("token") or "")
    if not answer.strip():
        raise RuntimeError("Vasuki V11 routing returned an empty answer.")

    # V14 selective repair: only severe quality failures are retried, and only
    # for automatic routing. This avoids adding latency to normal good answers.
    if provider == "auto":
        try:
            query=last_user_query(messages)
            review=critic_review(
                query,
                answer,
                sources=[{"type":"provided_context"}] if web_context.strip() else [],
                current_required=require_current,
            )
            issue_text=" ".join(review.issues).casefold()
            severe_issue=any(
                token in issue_text
                for token in ("placeholder", "empty answer", "incomplete content")
            )
            if review.needs_repair and (review.score < 60.0 or severe_issue):
                repair_messages=[
                    *messages,
                    {"role":"assistant","content":answer.strip()},
                    {"role":"user","content":review.repair_instruction},
                ]
                repaired=""
                repair_provider=""
                async for event in route_chat_stream_v11(
                    "auto",
                    repair_messages,
                    settings_arg,
                    web_context,
                    require_current=require_current,
                    as_of=as_of,
                    cache_bypass=True,
                    exclude_provider=provider_name or None,
                ):
                    if event.get("type")=="provider":
                        repair_provider=str(event.get("provider") or "")
                    elif event.get("type")=="token":
                        repaired+=str(event.get("token") or "")
                if repaired.strip():
                    answer=repaired.strip()
                    provider_name=repair_provider or provider_name
        except Exception:
            pass

    return answer.strip(),provider_name or "auto"

# Existing production chat endpoints now flow through V11's transparent judge/learning layer.
v10.legacy.route_chat = route_chat_v11
v10.v5.route_chat_stream_v5 = route_chat_stream_v11

async def _tool_web_search(query: str, max_results: int = 6):
    results,provider=await v10.legacy.search_web(query,settings,max_results,require_current=True)
    return {"provider":provider,"results":results}

async def _tool_calculator(expression: str):
    return {"expression":expression,"result":safe_calculate(expression)}

async def _tool_github_read(repo: str, path: str, ref: str="main"):
    return await read_repo_file(settings,repo,path,ref)

async def _tool_research(query: str):
    return await run_research(query,settings)

async def _tool_code_graph(files: dict[str,str]):
    graph=build_knowledge_graph(files)
    return {"nodes":graph.nodes,"edges":graph.edges}

TOOLS.register("web.search","read",_tool_web_search)
TOOLS.register("calculator.run","read",_tool_calculator)
TOOLS.register("github.read","read",_tool_github_read)
TOOLS.register("research.run","read",_tool_research)
TOOLS.register("code.graph","read",_tool_code_graph)

class JudgeRequest(BaseModel):
    prompt: str = Field(max_length=30000)
    answer: str = Field(max_length=100000)
    expected: str = Field(default="", max_length=30000)
    required_terms: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)

class CitationRequest(BaseModel):
    answer: str = Field(max_length=100000)
    sources: list[dict[str, Any]] = Field(default_factory=list)

class ProviderFeedbackRequest(BaseModel):
    provider: str
    task_type: str = "general"
    rating: str
    category: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

class ResearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=10000)
    project_id: str | None = None
    save_to_kb: bool = False
    title: str = ""

class CodeAgentRequest(BaseModel):
    instruction: str = Field(min_length=2, max_length=20000)
    files: dict[str, str]
    max_repair_attempts: int = Field(default=3, ge=1, le=5)
    test_errors: str = Field(default="", max_length=30000)

class GraphRequest(BaseModel):
    files: dict[str, str]
    project_id: str | None = None

class MemoryWriteRequest(BaseModel):
    key: str = Field(min_length=1, max_length=500)
    value: str = Field(min_length=1, max_length=12000)
    project_id: str | None = None
    source: str = "user"
    valid_from: str | None = None

class ToolExecuteRequest(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    permission_token: str | None = None

class PermissionRequest(BaseModel):
    action: str
    args: dict[str, Any] = Field(default_factory=dict)
    expires_seconds: int = Field(default=600, ge=60, le=3600)

class RetentionRequest(BaseModel):
    scope: str
    retention_days: int = Field(ge=0, le=3650)

class ScheduleRequest(BaseModel):
    title: str
    prompt: str
    run_at: str | None = None
    cron: str | None = None

class GithubReadFileRequest(BaseModel):
    repo: str
    path: str
    ref: str = "main"

class GithubIssueRequest(BaseModel):
    repo: str
    number: int

class GithubCompareRequest(BaseModel):
    repo: str
    base: str
    head: str


class GithubBranchRequest(BaseModel):
    repo: str
    branch: str
    from_ref: str = "main"
    permission_token: str

class GithubPutFileRequest(BaseModel):
    repo: str
    path: str
    content_base64: str
    message: str
    branch: str
    sha: str | None = None
    permission_token: str

class GithubPrRequest(BaseModel):
    repo: str
    title: str
    head: str
    base: str = "main"
    body: str = ""
    permission_token: str

class VideoRequest(BaseModel):
    prompt: str
    image_url: str | None = None
    duration_seconds: int = Field(default=6, ge=1, le=60)
    aspect_ratio: str = "16:9"
    camera: str = "cinematic"
    identity_lock: str = ""
    style_reference: str = ""
    pose: str = ""
    composition: str = ""
    reference_strength: float = Field(default=0.75, ge=0, le=1)

async def require_owner(user: AuthUser) -> None:
    status = await get_plan_status(user, settings)
    if not status.is_owner:
        raise HTTPException(status_code=403, detail="Owner access required.")

@app.middleware("http")
async def v11_reliability_middleware(request, call_next):
    started=time.perf_counter()
    subject=request.client.host if request.client else "unknown"
    abuse=abuse_check(subject,weight=1,limit_per_minute=int(getattr(settings,"v11_abuse_requests_per_minute",120)))
    if not abuse["allowed"]:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=429,content={"detail":"V11 abuse protection rate limit reached.","v11_abuse":abuse})
    try:
        response=await call_next(request)
        return response
    finally:
        record_request(route=request.url.path,status=getattr(locals().get("response",None),"status_code",500),latency_ms=(time.perf_counter()-started)*1000)

@app.get("/api/v11/capabilities")
async def capabilities(_user: AuthUser = Depends(get_current_user)):
    return {"ok":True,"capabilities":capability_registry(settings)}

@app.get("/health/v11")
async def health_v11():
    caps=capability_registry(settings)
    return {"ok":True,"version":"v11","capabilities":caps,"slo":slo_snapshot(),"provider_learning":provider_snapshot()}

@app.post("/api/v11/judge")
async def automatic_judge(payload: JudgeRequest, _user: AuthUser = Depends(get_current_user)):
    return {"ok":True,"judge":judge_answer(payload.prompt,payload.answer,expected=payload.expected,required_terms=payload.required_terms,sources=payload.sources)}

@app.post("/api/v11/citations/check")
async def citations_check(payload: CitationRequest, _user: AuthUser = Depends(get_current_user)):
    return {"ok":True,"verification":citation_fact_check(payload.answer,payload.sources)}

@app.post("/api/owner/v11/evals/run")
async def eval_run(
    live: bool = Query(False),
    limit: int = Query(400,ge=1,le=500),
    release: str = Query("v11",max_length=100),
    categories: str = Query(""),
    user: AuthUser = Depends(get_current_user),
):
    await require_owner(user)
    wanted=[x.strip() for x in categories.split(",") if x.strip()] or None
    return await run_eval(settings,release=release,live=live,categories=wanted,limit=limit,concurrency=int(getattr(settings,"v11_eval_concurrency",3)))

@app.post("/api/v11/providers/feedback")
async def provider_feedback(payload: ProviderFeedbackRequest, _user: AuthUser = Depends(get_current_user)):
    value=100.0 if payload.rating.lower().startswith("u") else 0.0
    await persist_provider_signal(settings,payload.provider,payload.task_type,"feedback_up" if value else "feedback_down",value,{"category":payload.category,**payload.metadata})
    return {"ok":True,"learning":provider_snapshot()}

@app.get("/api/owner/v11/providers/quality")
async def providers_quality(user: AuthUser = Depends(get_current_user)):
    await require_owner(user)
    return {"ok":True,"learning":provider_snapshot()}

@app.post("/api/v11/research/plan-run")
async def research_plan_run(payload: ResearchRequest, user: AuthUser = Depends(get_current_user)):
    report=await run_research(payload.query,settings,max_subquestions=int(getattr(settings,"v11_research_max_subquestions",6)))
    if payload.save_to_kb:
        report["saved_kb"]=await save_to_research_kb(settings,user.id,payload.project_id,payload.title or payload.query[:120],payload.query,report)
    return report

@app.post("/api/v11/code/agent")
async def code_agent(payload: CodeAgentRequest, _user: AuthUser = Depends(get_current_user)):
    total=sum(len(v) for v in payload.files.values())
    if len(payload.files)>80 or total>350000:
        raise HTTPException(status_code=413,detail="Project snapshot is too large for one V11 coding-agent request.")
    return await repair_loop(payload.instruction,payload.files,settings,max_attempts=payload.max_repair_attempts,external_test_errors=payload.test_errors)

@app.post("/api/v11/code/graph")
async def code_graph(payload: GraphRequest, user: AuthUser = Depends(get_current_user)):
    graph=build_knowledge_graph(payload.files)
    if payload.project_id and store.configured(settings):
        try:
            await store.request(settings,"DELETE","v11_project_graph_nodes",params={"user_id":f"eq.{user.id}","project_id":f"eq.{payload.project_id}"})
            await store.request(settings,"DELETE","v11_project_graph_edges",params={"user_id":f"eq.{user.id}","project_id":f"eq.{payload.project_id}"})
            node_rows=[{"user_id":user.id,"project_id":payload.project_id,"node_key":n["id"],"kind":n["kind"],"name":n["name"],"path":n["path"],"metadata":n.get("meta") or {}} for n in graph.nodes]
            edge_rows=[{"user_id":user.id,"project_id":payload.project_id,"from_key":str(e.get("from") or ""),"to_key":str(e.get("to") or ""),"edge_type":str(e.get("type") or "related"),"metadata":{}} for e in graph.edges]
            if node_rows: await store.request(settings,"POST","v11_project_graph_nodes",json_body=node_rows)
            if edge_rows: await store.request(settings,"POST","v11_project_graph_edges",json_body=edge_rows)
        except Exception:
            pass
    return {"ok":True,"nodes":graph.nodes,"edges":graph.edges,"persisted":bool(payload.project_id and store.configured(settings))}

@app.get("/api/v11/code/sandbox")
async def code_sandbox(_user: AuthUser = Depends(get_current_user)):
    return {"ok":True,"policy":sandbox_policy()}

@app.post("/api/v11/memory")
async def memory_write(payload: MemoryWriteRequest, user: AuthUser = Depends(get_current_user)):
    row=await upsert_temporal_memory(settings,user_id=user.id,project_id=payload.project_id,key=payload.key,value=payload.value,source=payload.source,valid_from=payload.valid_from)
    return {"ok":True,"memory":row}

@app.get("/api/v11/memory")
async def memory_read(project_id: str|None=None,user: AuthUser=Depends(get_current_user)):
    rows=await active_memory(settings,user_id=user.id,project_id=project_id)
    return {"ok":True,"memory":resolve_conflicts_v12(rows)}

@app.post("/api/v11/permissions/grant")
async def permission_grant(payload: PermissionRequest,user: AuthUser=Depends(get_current_user)):
    return {"ok":True,"permission":await grant_once(settings,user_id=user.id,action=payload.action,args=payload.args,expires_seconds=payload.expires_seconds)}

@app.get("/api/v11/tools")
async def tools(_user: AuthUser=Depends(get_current_user)):
    return {"ok":True,**registry_snapshot()}

@app.post("/api/v11/tools/execute")
async def tools_execute(payload: ToolExecuteRequest,user: AuthUser=Depends(get_current_user)):
    try:
        level=TOOLS.level(payload.name)
    except KeyError:
        raise HTTPException(status_code=404,detail="Unknown V11 tool.")
    if level!="read":
        allowed=await consume_permission(settings,user_id=user.id,action=payload.name,args=payload.args,token=payload.permission_token)
        if not allowed: raise HTTPException(status_code=403,detail="Explicit one-time permission required.")
    try:
        result=await TOOLS.execute(payload.name,**payload.args)
    except TypeError as exc:
        raise HTTPException(status_code=422,detail=f"Invalid tool arguments: {exc}")
    return {"ok":True,"tool":payload.name,"permission":level,"result":result}

@app.post("/api/v11/schedules")
async def schedules(payload: ScheduleRequest,user: AuthUser=Depends(get_current_user)):
    if not payload.run_at and not payload.cron:
        raise HTTPException(status_code=422,detail="run_at or cron is required.")
    row=await create_task(settings,user_id=user.id,title=payload.title,prompt=payload.prompt,run_at=payload.run_at,cron=payload.cron)
    return {"ok":True,"task":row,"runtime_note":runtime_note()}

@app.get("/api/owner/v11/slo")
async def slo(user: AuthUser=Depends(get_current_user)):
    await require_owner(user)
    return {"ok":True,"slo":slo_snapshot()}

@app.get("/api/owner/v11/db-performance")
async def db_perf(user: AuthUser=Depends(get_current_user)):
    await require_owner(user)
    return {"ok":True,"performance":await db_performance(settings)}

@app.get("/api/v11/privacy")
async def privacy(user: AuthUser=Depends(get_current_user)):
    return {"ok":True,"privacy":await privacy_snapshot(settings,user.id),"retention_defaults":RETENTION_DEFAULTS,"retention":await retention_policies(settings,user.id)}

@app.put("/api/v11/privacy/retention")
async def privacy_retention(payload: RetentionRequest,user: AuthUser=Depends(get_current_user)):
    try:
        row=await set_retention_policy(settings,user.id,payload.scope,payload.retention_days)
    except ValueError as exc:
        raise HTTPException(status_code=422,detail=str(exc))
    return {"ok":True,"policy":row,"retention":await retention_policies(settings,user.id)}

@app.post("/api/owner/v11/retention/cleanup")
async def retention_cleanup(user: AuthUser=Depends(get_current_user)):
    await require_owner(user)
    return {"ok":True,"cleanup":await cleanup_v11_tables(settings)}

@app.get("/api/v11/release")
async def release_channel(user: AuthUser=Depends(get_current_user)):
    status=await get_plan_status(user,settings)
    percent=int(getattr(settings,"v11_canary_percent",5))
    return {"ok":True,"release":release_for_user(user.id,stable="v10",canary="v11",percent=percent,owner=status.is_owner),"canary_percent":percent}

@app.post("/api/owner/v11/rollback")
async def rollback_release(reason: str=Body(...,embed=True),user: AuthUser=Depends(get_current_user)):
    await require_owner(user)
    return {"ok":True,"rollback":await rollback(settings,reason=reason)}

@app.post("/api/v11/github/file")
async def github_file(payload: GithubReadFileRequest,_user: AuthUser=Depends(get_current_user)):
    return {"ok":True,"data":await read_repo_file(settings,payload.repo,payload.path,payload.ref)}

@app.post("/api/v11/github/issue")
async def github_issue_read(payload: GithubIssueRequest,_user: AuthUser=Depends(get_current_user)):
    return {"ok":True,"data":await github_issue(settings,payload.repo,payload.number)}

@app.post("/api/v11/github/compare")
async def github_compare_read(payload: GithubCompareRequest,_user: AuthUser=Depends(get_current_user)):
    return {"ok":True,"data":await github_compare(settings,payload.repo,payload.base,payload.head)}

@app.post("/api/v11/github/branch")
async def github_branch(payload: GithubBranchRequest,user: AuthUser=Depends(get_current_user)):
    args={"repo":payload.repo,"branch":payload.branch,"from_ref":payload.from_ref}
    allowed=await consume_permission(settings,user_id=user.id,action="github.branch.create",args=args,token=payload.permission_token)
    if not allowed: raise HTTPException(status_code=403,detail="Explicit one-time permission is required for branch creation.")
    return {"ok":True,"data":await github_create_branch(settings,payload.repo,branch=payload.branch,from_ref=payload.from_ref)}

@app.post("/api/v11/github/file-write")
async def github_file_write(payload: GithubPutFileRequest,user: AuthUser=Depends(get_current_user)):
    args={"repo":payload.repo,"path":payload.path,"message":payload.message,"branch":payload.branch,"sha":payload.sha}
    allowed=await consume_permission(settings,user_id=user.id,action="github.file.write",args=args,token=payload.permission_token)
    if not allowed: raise HTTPException(status_code=403,detail="Explicit one-time permission is required for GitHub file writes.")
    return {"ok":True,"data":await github_put_file(settings,payload.repo,path=payload.path,content_b64=payload.content_base64,message=payload.message,branch=payload.branch,sha=payload.sha)}

@app.post("/api/v11/github/pr")
async def github_pr(payload: GithubPrRequest,user: AuthUser=Depends(get_current_user)):
    args={"repo":payload.repo,"title":payload.title,"head":payload.head,"base":payload.base,"body":payload.body}
    allowed=await consume_permission(settings,user_id=user.id,action="github.pr.create",args=args,token=payload.permission_token)
    if not allowed: raise HTTPException(status_code=403,detail="Explicit one-time permission is required for PR creation.")
    return {"ok":True,"data":await github_create_pr(settings,payload.repo,title=payload.title,head=payload.head,base=payload.base,body=payload.body)}

@app.post("/api/v11/image/consistency")
async def image_consistency(
    prompt: str = Form(...),
    identity_lock: str = Form(""),
    style_reference: str = Form(""),
    pose: str = Form(""),
    composition: str = Form(""),
    reference_strength: float = Form(0.75),
    reference_image: UploadFile | None = File(None),
    _user: AuthUser = Depends(get_current_user),
):
    enriched=consistency_prompt(prompt,identity=identity_lock,style=style_reference,pose=pose,composition=composition,reference_strength=reference_strength)
    if reference_image is not None:
        content=await reference_image.read()
        if len(content)>15*1024*1024:
            raise HTTPException(status_code=413,detail="Reference image exceeds 15 MB.")
        result=await process_vision_request(content=content,filename=reference_image.filename or "reference.png",mime_type=reference_image.content_type or "image/png",prompt=enriched,operation="edit",settings=settings)
        mode="reference-image-edit"
    else:
        result=await route_image_v10("auto",enriched,settings)
        mode="text-generation"
    return {"ok":True,"mode":mode,"controls":{"identity_lock":identity_lock,"style_reference":style_reference,"pose":pose,"composition":composition,"reference_strength":reference_strength},"result":result}

@app.post("/api/v11/image/masked-edit")
async def image_masked_edit(
    image: UploadFile = File(...),
    mask: UploadFile = File(...),
    prompt: str = Form(...),
    _user: AuthUser = Depends(get_current_user),
):
    original=await image.read()
    mask_bytes=await mask.read()
    if len(original)>15*1024*1024 or len(mask_bytes)>15*1024*1024:
        raise HTTPException(status_code=413,detail="Image or mask exceeds 15 MB.")
    edited=await process_vision_request(content=original,filename=image.filename or "image.png",mime_type=image.content_type or "image/png",prompt=prompt,operation="edit",settings=settings)
    url=str(edited.get("url") or "")
    if not url.startswith("data:") or "," not in url:
        raise HTTPException(status_code=502,detail="Image edit provider did not return an inline image for mask compositing.")
    import base64
    edited_bytes=base64.b64decode(url.split(",",1)[1])
    final_bytes=apply_mask_composite(original,edited_bytes,mask_bytes)
    final_url="data:image/png;base64,"+base64.b64encode(final_bytes).decode("ascii")
    return {"ok":True,"url":final_url,"provider":edited.get("provider"),"operation":"masked-edit"}

@app.post("/api/v11/video/generate")
async def video_generate(payload: VideoRequest,_user: AuthUser=Depends(get_current_user)):
    prompt=consistency_prompt(payload.prompt,identity=payload.identity_lock,style=payload.style_reference,pose=payload.pose,composition=payload.composition,reference_strength=payload.reference_strength)
    return {"ok":True,**await generate_video(settings,prompt=prompt,image_url=payload.image_url,duration_seconds=payload.duration_seconds,aspect_ratio=payload.aspect_ratio,camera=payload.camera)}

@app.post("/api/v11/audio/tts")
async def tts(text: str=Form(...),voice: str=Form("alloy"),_user: AuthUser=Depends(get_current_user)):
    audio=await server_tts(settings,text=text,voice=voice)
    return Response(content=audio,media_type="audio/mpeg")

@app.post("/api/v11/audio/stt")
async def stt(file: UploadFile=File(...),_user: AuthUser=Depends(get_current_user)):
    data=await file.read()
    return {"ok":True,"result":await server_stt(settings,audio=data,filename=file.filename or "audio.webm")}

def _extract_upload(name: str,data: bytes)->str:
    lower=name.lower()
    if lower.endswith(".pdf"):
        reader=PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages)[:80000]
    if lower.endswith(".docx"):
        doc=Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)[:80000]
    if lower.endswith((".txt",".md",".csv",".json",".py",".js",".ts",".tsx",".html",".css")):
        return data.decode("utf-8",errors="replace")[:80000]
    return ""

@app.post("/api/v11/multimodal")
async def multimodal(
    prompt: str=Form(...),
    files: list[UploadFile]=File(default=[]),
    user: AuthUser=Depends(get_current_user),
):
    if len(files)>8: raise HTTPException(status_code=413,detail="Maximum 8 files per multimodal request.")
    contexts=[]; audio_notes=[]
    for file in files:
        data=await file.read()
        if len(data)>15*1024*1024: raise HTTPException(status_code=413,detail=f"{file.filename}: file exceeds 15 MB.")
        text=_extract_upload(file.filename or "",data)
        content_type=(file.content_type or "").lower()
        if content_type.startswith("image/"):
            try:
                vision=await process_vision_request(
                    content=data,
                    filename=file.filename or "image.png",
                    mime_type=content_type,
                    prompt="Extract all visible facts, text, objects, relationships and details needed for a later joint multimodal answer.",
                    operation="analyze",
                    settings=settings,
                )
                contexts.append(f"IMAGE: {file.filename}\n{str(vision.get('answer') or '')[:30000]}")
            except Exception as exc:
                contexts.append(f"IMAGE: {file.filename}\nVisual decoding unavailable ({str(exc)[:300]}).")
        elif text:
            contexts.append(f"FILE: {file.filename}\n{text}")
        elif (file.filename or "").lower().endswith(".pdf"):
            try:
                vision=await process_vision_request(
                    content=data,
                    filename=file.filename or "document.pdf",
                    mime_type="application/pdf",
                    prompt="Extract and summarize all readable document content needed for a later joint multimodal answer.",
                    operation="analyze",
                    settings=settings,
                )
                contexts.append(f"PDF: {file.filename}\n{str(vision.get('answer') or '')[:50000]}")
            except Exception as exc:
                contexts.append(f"PDF: {file.filename}\nPDF decoding unavailable ({str(exc)[:300]}).")
        elif content_type.startswith("audio/"):
            try:
                transcript=await server_stt(settings,audio=data,filename=file.filename or "audio.webm")
                audio_notes.append(f"AUDIO {file.filename}: {json.dumps(transcript,ensure_ascii=False)[:15000]}")
            except Exception as exc:
                audio_notes.append(f"AUDIO {file.filename}: transcription unavailable ({str(exc)[:200]})")
        else:
            contexts.append(f"FILE: {file.filename}\nAttachment metadata: content-type={file.content_type}; size={len(data)} bytes.")
    context="\n\n".join([*contexts,*audio_notes])[:120000]
    full=f"""User request: {prompt}

Joint multimodal context:
{context}

Reason jointly across the request and all supplied context. Clearly state if an image/audio binary could not be semantically decoded by this endpoint."""
    answer,provider=await route_chat_v10("auto",[{"role":"user","content":full}],settings,context)
    return {"ok":True,"answer":answer,"provider":provider,"files":len(files),"contract":multimodal_contract()}

async def _scheduled_executor(row: dict[str,Any])->dict[str,Any]:
    answer,provider=await route_chat_v10("auto",[{"role":"user","content":str(row.get("prompt") or "")}],settings,"")
    return {"answer":answer[:40000],"provider":provider}

@app.post("/api/owner/v11/scheduler/tick")
async def scheduler_manual_tick(user: AuthUser=Depends(get_current_user)):
    await require_owner(user)
    return {"ok":True,"tick":await scheduler_tick(settings,_scheduled_executor),"note":runtime_note()}


# VASUKI_V12_CORE_RELIABILITY
app.include_router(v12_router)

# VASUKI_V13_BATCH2_AUTONOMY
class V13MessagesRequest(BaseModel):
    messages: list[dict[str, Any]]
    require_current: bool = False


class V13CriticRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=30000)
    answer: str = Field(min_length=1, max_length=100000)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    current_required: bool = False


class V13RecoveryRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=100)
    error: str = Field(min_length=1, max_length=10000)
    candidates: list[str] = Field(default_factory=list)


class V13ProjectRequest(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class V13DeploymentRequest(BaseModel):
    changed_paths: list[str] = Field(default_factory=list)
    tests_passed: bool = False
    backup_ready: bool = False
    pending_migrations: list[str] = Field(default_factory=list)
    secrets_exposed: bool = False


@app.get("/health/v13")
async def health_v13():
    snapshot = provider_snapshot_v12(settings)
    return {
        "ok": True,
        "version": "v13",
        "features": [
            "intent-brain-v2",
            "autonomous-orchestrator",
            "multi-role-execution-planner",
            "answer-critic",
            "incident-recovery-planner",
            "project-brain",
            "provider-health-analytics",
            "deployment-guard",
            "image-identity-lock",
            "context-compression",
        ],
        "provider_health": provider_health_summary(snapshot),
    }


@app.post("/api/v13/orchestrate")
async def v13_orchestrate(
    payload: V13MessagesRequest,
    _user: AuthUser = Depends(get_current_user),
):
    if not payload.messages:
        raise HTTPException(status_code=422, detail="At least one message is required.")
    decision = orchestrate_request(
        payload.messages,
        require_current=payload.require_current,
    )
    return {"ok": True, "decision": decision.to_dict()}


@app.post("/api/v13/plan")
async def v13_plan(
    payload: V13MessagesRequest,
    _user: AuthUser = Depends(get_current_user),
):
    if not payload.messages:
        raise HTTPException(status_code=422, detail="At least one message is required.")
    plan = build_execution_plan(
        payload.messages,
        require_current=payload.require_current,
    )
    return {"ok": True, "plan": plan.to_dict()}


@app.post("/api/v13/critic")
async def v13_critic(
    payload: V13CriticRequest,
    _user: AuthUser = Depends(get_current_user),
):
    result = critic_review(
        payload.prompt,
        payload.answer,
        sources=payload.sources,
        current_required=payload.current_required,
    )
    return {"ok": True, "critic": result.to_dict()}


@app.post("/api/v13/incidents/recovery")
async def v13_incident_recovery(
    payload: V13RecoveryRequest,
    _user: AuthUser = Depends(get_current_user),
):
    result = recovery_plan(
        payload.provider,
        payload.error,
        payload.candidates,
    )
    return {"ok": True, "recovery": result.to_dict()}


@app.post("/api/v13/project/snapshot")
async def v13_project_snapshot(
    payload: V13ProjectRequest,
    _user: AuthUser = Depends(get_current_user),
):
    return {"ok": True, "project": project_snapshot(payload.items)}


@app.post("/api/v13/deployment/check")
async def v13_deployment_check(
    payload: V13DeploymentRequest,
    _user: AuthUser = Depends(get_current_user),
):
    result = check_deployment(
        payload.changed_paths,
        tests_passed=payload.tests_passed,
        backup_ready=payload.backup_ready,
        pending_migrations=payload.pending_migrations,
        secrets_exposed=payload.secrets_exposed,
    )
    return {"ok": True, "deployment": result.to_dict()}


@app.get("/api/owner/v13/providers/health")
async def v13_provider_health(
    user: AuthUser = Depends(get_current_user),
):
    await require_owner(user)
    return {
        "ok": True,
        "health": provider_health_summary(provider_snapshot_v12(settings)),
    }

# VASUKI_V14_RUNTIME_QUALITY
@app.get("/health/v14")
async def health_v14():
    return {
        "ok": True,
        **runtime_health(),
        "v13_provider_health": provider_health_summary(
            provider_snapshot_v12(settings)
        ),
    }


class V14RuntimeInspectRequest(BaseModel):
    messages: list[dict[str, Any]]
    require_current: bool = False


@app.post("/api/v14/runtime/inspect")
async def v14_runtime_inspect(
    payload: V14RuntimeInspectRequest,
    _user: AuthUser = Depends(get_current_user),
):
    if not payload.messages:
        raise HTTPException(
            status_code=422,
            detail="At least one message is required.",
        )
    from app.v14.runtime import decide_runtime
    decision = decide_runtime(
        payload.messages,
        require_current=payload.require_current,
    )
    return {"ok": True, "runtime": decision.to_dict()}

# VASUKI_V15_AUTONOMOUS_CODER
class V15CodeProjectRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=30000)


class V15CodePackageRequest(BaseModel):
    project_name: str = Field(default="vasuki-project", max_length=120)
    summary: str = Field(default="", max_length=5000)
    language: str = Field(default="mixed", max_length=120)
    framework: str = Field(default="custom", max_length=160)
    files: list[dict[str, Any]] = Field(default_factory=list)
    powershell: list[str] = Field(default_factory=list)
    run_commands: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


async def _v15_generate_project(
    user_prompt: str,
    *,
    existing_files: list[dict[str, str]] | None = None,
) -> tuple[dict[str, Any], str]:
    planner = build_execution_plan(
        [{"role": "user", "content": user_prompt}],
        require_current=False,
    ).to_dict()
    generation_prompt = build_project_prompt(
        user_prompt,
        planner_context=planner,
        existing_files=existing_files,
    )
    messages = [
        {"role": "system", "content": V15_PROJECT_SYSTEM_PROMPT},
        {"role": "user", "content": generation_prompt},
    ]

    last_error = ""
    for attempt in range(3):
        try:
            raw, provider_name = await route_chat_v11(
                "auto",
                messages,
                settings,
                "",
                require_current=False,
            )
            project = parse_project_response(raw)
            if existing_files:
                project = merge_existing_files(
                    existing_files, project
                )
            return project, provider_name
        except Exception as exc:
            last_error = str(exc)
            if attempt < 2:
                await asyncio.sleep((0.8, 1.8)[attempt])

    raise HTTPException(
        status_code=503,
        detail=(
            "V15 coding providers are temporarily unavailable after "
            f"automatic retries. {last_error[:500]}"
        ),
    )


@app.get("/health/v15")
async def health_v15():
    return {
        "ok": True,
        **coder_health(),
        "provider_health": provider_health_summary(
            provider_snapshot_v12(settings)
        ),
    }


@app.post("/api/v15/code/project")
async def v15_code_project(
    payload: V15CodeProjectRequest,
    _user: AuthUser = Depends(get_current_user),
):
    project, provider_name = await _v15_generate_project(
        payload.prompt
    )
    return package_project_response(
        project,
        provider=provider_name or "vasuki-v15",
    )


@app.post("/api/v15/code/package")
async def v15_code_package(
    payload: V15CodePackageRequest,
    _user: AuthUser = Depends(get_current_user),
):
    try:
        project = normalize_project_payload(
            payload.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=str(exc)
        ) from exc
    return package_project_response(
        project, provider="vasuki-v15-packager"
    )


@app.post("/api/v15/code/modify")
async def v15_code_modify(
    prompt: str = Form(...),
    file: UploadFile = File(...),
    _user: AuthUser = Depends(get_current_user),
):
    filename = file.filename or "project.zip"
    if not filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=415,
            detail=(
                "V15 project modification currently accepts "
                "a .zip project."
            ),
        )
    data = await file.read()
    try:
        existing_files = extract_zip_text_files(data)
    except (ValueError, zipfile.BadZipFile) as exc:
        raise HTTPException(
            status_code=422, detail=str(exc)
        ) from exc

    project, provider_name = await _v15_generate_project(
        prompt,
        existing_files=existing_files,
    )
    return package_project_response(
        project,
        provider=provider_name or "vasuki-v15",
    )
