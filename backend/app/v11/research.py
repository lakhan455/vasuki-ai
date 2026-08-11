from __future__ import annotations
import asyncio, json, re, uuid
from typing import Any

import app.main as legacy
from app.services.chat_v10 import route_chat_v10
from app.v11 import store
from app.v11.quality import citation_fact_check

def _json_from_text(value: str) -> Any:
    value=(value or "").strip()
    fence=re.search(r"```(?:json)?\s*([\s\S]*?)```",value,re.I)
    if fence: value=fence.group(1).strip()
    start=min([p for p in (value.find("{"),value.find("[")) if p>=0],default=-1)
    if start>=0: value=value[start:]
    for endchar in ("}","]"):
        end=value.rfind(endchar)
        if end>=0:
            candidate=value[:end+1]
            try: return json.loads(candidate)
            except Exception: pass
    return None

async def plan_query(query: str, settings, *, max_subquestions: int=6) -> dict[str, Any]:
    prompt=f"""You are Vasuki Research Planner V3.
Break the research request into 3-{max_subquestions} independent evidence questions.
Return strict JSON only:
{{"objective":"...","subquestions":[{{"id":"q1","question":"...","why":"...","requires_current":true}}],"conflicts_to_check":["..."]}}
Request: {query}"""
    answer,provider=await route_chat_v10("auto",[{"role":"user","content":prompt}],settings,"",require_current=False)
    data=_json_from_text(answer)
    if not isinstance(data,dict) or not isinstance(data.get("subquestions"),list):
        data={"objective":query,"subquestions":[{"id":"q1","question":query,"why":"primary question","requires_current":True}],"conflicts_to_check":[]}
    data["provider"]=provider
    data["subquestions"]=data["subquestions"][:max_subquestions]
    return data

async def _search_one(item: dict[str, Any], settings, max_results: int) -> dict[str, Any]:
    question=str(item.get("question") or "").strip()
    results,provider=await legacy.search_web(question,settings,max_results,require_current=bool(item.get("requires_current",False)))
    return {"id":item.get("id"),"question":question,"provider":provider,"results":results}

def _evidence_context(rows: list[dict[str, Any]]) -> tuple[str,list[dict[str,Any]]]:
    context=[]; sources=[]
    n=0
    for row in rows:
        for item in row.get("results") or []:
            if not isinstance(item,dict): continue
            n+=1
            title=str(item.get("title") or "Source")
            url=str(item.get("url") or "")
            snippet=str(item.get("content") or item.get("snippet") or item.get("text") or "")
            context.append(f"[S{n}] {title}\nURL: {url}\nEvidence: {snippet[:1800]}")
            sources.append({"id":f"S{n}","title":title,"url":url,"snippet":snippet[:4000]})
            if n>=30: return "\n\n".join(context),sources
    return "\n\n".join(context),sources

async def run_research(query: str, settings, *, max_subquestions: int=6, results_per_question: int=5) -> dict[str, Any]:
    plan=await plan_query(query,settings,max_subquestions=max_subquestions)
    tasks=[_search_one(item,settings,results_per_question) for item in plan["subquestions"]]
    evidence_rows=await asyncio.gather(*tasks,return_exceptions=True)
    clean=[]
    for item,result in zip(plan["subquestions"],evidence_rows):
        if isinstance(result,Exception):
            clean.append({"id":item.get("id"),"question":item.get("question"),"provider":"","results":[],"error":str(result)[:500]})
        else: clean.append(result)
    context,sources=_evidence_context(clean)
    synthesis=f"""You are Vasuki Research Planner V3 final synthesizer.
Answer the request using ONLY the evidence below. Resolve conflicts explicitly. Every important factual claim must cite [S#].
If evidence is insufficient, say so. Do not invent citations.

REQUEST:
{query}

EVIDENCE:
{context}

Return a concise but complete research report with:
1. Answer
2. Evidence-backed findings
3. Conflicts/uncertainties
4. Conclusion
"""
    answer,provider=await route_chat_v10("auto",[{"role":"user","content":synthesis}],settings,context,require_current=True)
    check=citation_fact_check(answer,sources)
    return {"ok":True,"query":query,"plan":plan,"searches":clean,"sources":sources,"answer":answer,"provider":provider,"citation_check":check}

async def save_to_research_kb(settings, user_id: str, project_id: str | None, title: str, query: str, report: dict[str, Any]) -> dict[str, Any]:
    row={"id":str(uuid.uuid4()),"user_id":user_id,"project_id":project_id,"title":title[:200],"query":query[:5000],"answer":str(report.get("answer") or "")[:60000],"sources":report.get("sources") or [],"verification":report.get("citation_check") or {}}
    if store.configured(settings):
        saved=await store.request(settings,"POST","v11_research_kb",json_body=row)
        if isinstance(saved,list) and saved: return saved[0]
    return row
