from __future__ import annotations
import asyncio, json, math, re, time, uuid
from collections import defaultdict, deque
from pathlib import Path
from threading import Lock
from typing import Any

from app.services.chat_v10 import route_chat_v10
from app.services.quality_v9 import provider_score as v9_provider_score
from app.v11 import store

_WORD = re.compile(r"[A-Za-z0-9_]+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_LOCK = Lock()
_OBS: dict[str, dict[str, deque[float]]] = defaultdict(lambda: defaultdict(lambda: deque(maxlen=500)))

def _tokens(text: str) -> set[str]:
    return {m.group(0).casefold() for m in _WORD.finditer(text or "") if len(m.group(0)) > 2}

def _overlap(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return 0.0 if not ta or not tb else len(ta & tb) / max(1, len(ta))

def _bounded(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)

def judge_answer(prompt: str, answer: str, *, expected: str = "", required_terms: list[str] | None = None, sources: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    answer = (answer or "").strip()
    prompt = (prompt or "").strip()
    expected = (expected or "").strip()
    required_terms = required_terms or []
    sources = sources or []
    expected_score = 65.0 if not expected else 100.0 * _overlap(expected, answer)
    req_hits = sum(1 for term in required_terms if str(term).casefold() in answer.casefold())
    req_score = 100.0 if not required_terms else 100.0 * req_hits / len(required_terms)
    completeness = 45.0 if not answer else min(100.0, 45.0 + math.log2(max(2, len(answer))) * 6.5)
    if len(prompt) > 800 and len(answer) < 250:
        completeness -= 20.0
    has_code = bool(re.search(r"\b(code|python|javascript|typescript|react|html|css|sql|debug)\b", prompt, re.I))
    code_blocks = re.findall(r"```[^\n]*\n([\s\S]*?)```", answer)
    code_quality = 70.0 if not has_code else (88.0 if code_blocks else 30.0)
    if any("TODO" in block for block in code_blocks):
        code_quality -= 15.0
    cited = bool(re.search(r"https?://|\[[0-9]+\]|\bcitation\b|\bsource", answer, re.I))
    citation_score = 100.0 if (sources and cited) else (70.0 if not sources else 35.0)
    unsupported_specificity = len(re.findall(r"\b(?:19|20)\d{2}\b|\b\d+(?:\.\d+)?%\b", answer))
    hallucination_risk = 100.0 if not answer else 12.0 + unsupported_specificity * (7.0 if not sources else 2.5)
    correctness = _bounded(0.62 * expected_score + 0.38 * req_score)
    completeness = _bounded(completeness)
    code_quality = _bounded(code_quality)
    citation_score = _bounded(citation_score)
    hallucination_risk = _bounded(hallucination_risk)
    overall = _bounded(correctness*0.34 + completeness*0.24 + citation_score*0.16 + code_quality*0.16 + (100.0-hallucination_risk)*0.10)
    return {"overall": overall, "correctness": correctness, "completeness": completeness, "citations": citation_score, "code_quality": code_quality, "hallucination_risk": hallucination_risk, "signals": {"required_terms": len(required_terms), "required_terms_hit": req_hits, "code_blocks": len(code_blocks), "sources": len(sources)}}

def _claims(answer: str) -> list[str]:
    rows=[]
    for raw in _SENTENCE.split(answer or ""):
        text=raw.strip(" -*#\t")
        if len(text)>=25 and not re.search(r"\b(I think|maybe|perhaps|could|might)\b", text, re.I):
            rows.append(text[:700])
    return rows[:40]

def citation_fact_check(answer: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    source_texts=[]
    for source in sources or []:
        if not isinstance(source, dict): continue
        content=str(source.get("content") or source.get("snippet") or source.get("text") or source.get("title") or "").strip()
        if content:
            source_texts.append((str(source.get("url") or source.get("title") or "source"), content))
    results=[]; supported_count=0
    for claim in _claims(answer):
        best_score=0.0; best_source=""
        for label,content in source_texts:
            score=_overlap(claim,content)
            if score>best_score: best_score,best_source=score,label
        supported=best_score>=0.42
        supported_count += int(supported)
        results.append({"claim":claim,"supported":supported,"support_score":round(best_score,4),"source":best_source or None})
    total=len(results); coverage=100.0 if total==0 else 100.0*supported_count/total
    return {"claims":results,"claim_count":total,"supported_count":supported_count,"coverage":_bounded(coverage),"risk":"low" if coverage>=85 else ("medium" if coverage>=60 else "high")}

def observe_provider(provider: str, task_type: str, *, score: float | None = None, rating: str | None = None) -> None:
    provider=str(provider or "").replace("cache:","").strip()
    task_type=str(task_type or "general").strip().lower()
    if not provider: return
    values=[]
    if score is not None: values.append(max(0.0,min(1.0,float(score)/100.0)))
    if rating: values.append(1.0 if rating.lower().startswith("u") else 0.0)
    with _LOCK:
        for value in values: _OBS[task_type][provider].append(value)


async def persist_provider_signal(settings, provider: str, task_type: str, signal_type: str, signal_value: float, metadata: dict[str,Any] | None=None) -> None:
    observe_provider(provider,task_type,score=signal_value if signal_type!="feedback_down" else 0.0)
    if store.configured(settings):
        try:
            await store.request(settings,"POST","v11_provider_quality",json_body={
                "task_type":task_type,
                "provider":str(provider or "").replace("cache:",""),
                "signal_type":signal_type,
                "signal_value":float(signal_value),
                "metadata":metadata or {},
            })
        except Exception:
            pass

async def load_persisted_provider_learning(settings, limit: int=2000) -> int:
    if not store.configured(settings): return 0
    try:
        rows=await store.request(settings,"GET","v11_provider_quality",params={"select":"task_type,provider,signal_type,signal_value","order":"created_at.desc","limit":str(max(1,min(5000,limit)))}) or []
    except Exception:
        return 0
    loaded=0
    for row in reversed(rows):
        provider=str(row.get("provider") or "")
        task=str(row.get("task_type") or "general")
        value=float(row.get("signal_value") or 0)
        if row.get("signal_type")=="feedback_down": value=0.0
        elif value>1.0: value=value/100.0
        with _LOCK:
            if provider: _OBS[task][provider].append(max(0.0,min(1.0,value))); loaded+=1
    return loaded

def learned_quality(provider: str, task_type: str) -> float:
    with _LOCK: rows=list(_OBS.get(task_type,{}).get(provider,()))
    return 0.72 if not rows else (sum(rows)+5.0*0.72)/(len(rows)+5.0)

def provider_score_v11(provider: str, task_type: str) -> float:
    return round(float(v9_provider_score(provider,task_type))*0.72 + learned_quality(provider,task_type)*0.28,6)

def rank_for_task_v11(names: list[str], task_type: str="general") -> list[str]:
    rows=[(provider_score_v11(name,task_type)-i*0.004,name) for i,name in enumerate(names)]
    rows.sort(reverse=True)
    return [name for _,name in rows]

def provider_snapshot() -> dict[str, Any]:
    with _LOCK:
        return {task:{provider:{"observations":len(rows),"learned_quality":round((sum(rows)+3.6)/(len(rows)+5.0),4)} for provider,rows in providers.items()} for task,providers in _OBS.items()}

def load_eval_cases() -> list[dict[str, Any]]:
    path=Path(__file__).resolve().parents[1]/"data"/"evals_v11.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

async def _run_case(case: dict[str, Any], settings) -> dict[str, Any]:
    started=time.perf_counter(); category=str(case.get("category") or "chat")
    prompt=str(case.get("prompt") or ""); expected=str(case.get("expected") or "")
    required=[str(x) for x in case.get("required_terms") or []]
    provider=""; error=""; answer=""
    if case.get("execution")=="contract":
        answer=str(case.get("contract_answer") or expected); provider="contract"
    else:
        try:
            answer,provider=await route_chat_v10("auto",[{"role":"user","content":prompt}],settings,"",require_current=category=="research")
        except Exception as exc:
            error=f"{type(exc).__name__}: {str(exc)[:500]}"
    score=judge_answer(prompt,answer,expected=expected,required_terms=required,sources=case.get("sources") or [])
    if error: score["overall"]=0.0
    await persist_provider_signal(settings,provider,category,"benchmark",float(score["overall"]),{"case_id":case.get("id")})
    return {"id":case.get("id"),"category":category,"provider":provider,"answer":answer[:10000],"error":error,"score":score,"latency_ms":round((time.perf_counter()-started)*1000)}

async def run_eval(settings, *, release: str, live: bool, categories: list[str] | None=None, limit: int=400, concurrency: int=3) -> dict[str, Any]:
    cases=load_eval_cases()
    if categories:
        wanted={x.strip().lower() for x in categories}
        cases=[case for case in cases if str(case.get("category")).lower() in wanted]
    cases=cases[:max(1,min(500,limit))]
    if not live: cases=[dict(case,execution="contract") for case in cases]
    sem=asyncio.Semaphore(max(1,min(6,concurrency)))
    async def guarded(case):
        async with sem: return await _run_case(case,settings)
    run_id=str(uuid.uuid4()); started=time.perf_counter()
    results=await asyncio.gather(*(guarded(case) for case in cases))
    by_category=defaultdict(list)
    for row in results: by_category[row["category"]].append(float(row["score"]["overall"]))
    category_scores={k:round(sum(v)/max(1,len(v)),2) for k,v in sorted(by_category.items())}
    overall=round(sum(float(row["score"]["overall"]) for row in results)/max(1,len(results)),2)
    report={"run_id":run_id,"release":release,"mode":"live" if live else "contract","case_count":len(results),"score":overall,"category_scores":category_scores,"provider_learning":provider_snapshot(),"duration_ms":round((time.perf_counter()-started)*1000),"results":results}
    if store.configured(settings):
        try:
            await store.request(settings,"POST","v11_eval_runs",json_body={"id":run_id,"release":release,"mode":report["mode"],"case_count":len(results),"score":overall,"category_scores":category_scores})
        except Exception: pass
    return report
