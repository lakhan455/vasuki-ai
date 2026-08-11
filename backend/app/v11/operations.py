from __future__ import annotations
import hashlib, statistics, time
from collections import deque
from threading import Lock
from typing import Any
import httpx
from app.v11 import store

_LOCK=Lock()
_SAMPLES=deque(maxlen=5000)
_ABUSE={}

def record_request(*, route: str,status: int,latency_ms: float,first_token_ms: float|None=None,provider: str="",fallback: bool=False)->None:
    row={"ts":time.time(),"route":route,"status":int(status),"latency_ms":float(latency_ms),"first_token_ms":first_token_ms,"provider":provider,"fallback":bool(fallback)}
    with _LOCK:_SAMPLES.append(row)

def _pct(values:list[float],p:float)->float|None:
    if not values:return None
    rows=sorted(values); idx=min(len(rows)-1,max(0,round((len(rows)-1)*p)))
    return round(rows[idx],2)

def slo_snapshot()->dict[str,Any]:
    with _LOCK: rows=list(_SAMPLES)
    lat=[r["latency_ms"] for r in rows]
    ft=[r["first_token_ms"] for r in rows if r.get("first_token_ms") is not None]
    fallback_signals=[bool(r.get("fallback")) for r in rows]
    try:
        from app.services.telemetry_v7 import recent as chat_recent
        chat_rows=chat_recent(200)
        ft.extend(float(r["first_token_ms"]) for r in chat_rows if r.get("first_token_ms") is not None)
        fallback_signals.extend(int(r.get("attempts") or 0)>1 for r in chat_rows)
    except Exception:
        chat_rows=[]
    total=len(rows); success=sum(1 for r in rows if 200<=r["status"]<400)
    errors=sum(1 for r in rows if r["status"]>=500)
    return {
        "samples":total,
        "chat_samples":len(chat_rows),
        "p50_latency_ms":_pct(lat,0.50),
        "p95_latency_ms":_pct(lat,0.95),
        "p50_first_token_ms":_pct(ft,0.50),
        "p95_first_token_ms":_pct(ft,0.95),
        "success_pct":round(100*success/max(1,total),2),
        "fallback_pct":round(100*sum(1 for value in fallback_signals if value)/max(1,len(fallback_signals)),2),
        "error_pct":round(100*errors/max(1,total),2),
        "uptime_source":"process/health endpoint",
    }

def canary_bucket(user_id: str)->int:
    return int(hashlib.sha256(user_id.encode()).hexdigest()[:8],16)%100

def release_for_user(user_id: str, *, stable: str="v10", canary: str="v11", percent: int=5, owner: bool=False)->str:
    if owner:return canary
    return canary if canary_bucket(user_id)<max(0,min(100,percent)) else stable

async def rollback(settings, *, reason: str)->dict[str,Any]:
    url=str(getattr(settings,"v11_rollback_webhook_url","") or "").strip()
    if not url:return {"triggered":False,"reason":"No rollback webhook configured.","health_reason":reason}
    async with httpx.AsyncClient(timeout=20.0) as client:
        response=await client.post(url,json={"source":"vasuki-v11","action":"rollback","reason":reason})
    return {"triggered":response.status_code<400,"status":response.status_code,"response":response.text[:500]}

async def db_performance(settings)->dict[str,Any]:
    if not store.configured(settings):return {"configured":False}
    try:
        data=await store.rpc(settings,"v11_db_performance",{})
        return {"configured":True,"data":data}
    except Exception as exc:
        return {"configured":True,"available":False,"error":str(exc)[:500]}

def abuse_check(subject: str, *, weight: int=1, limit_per_minute: int=90)->dict[str,Any]:
    now=int(time.time()); window=now//60; key=(subject,window)
    current=_ABUSE.get(key,0)+max(1,weight); _ABUSE[key]=current
    for old in list(_ABUSE):
        if old[1]<window-2:_ABUSE.pop(old,None)
    return {"allowed":current<=limit_per_minute,"score":current,"limit":limit_per_minute,"reason":"rate anomaly" if current>limit_per_minute else ""}

async def privacy_snapshot(settings, user_id: str)->dict[str,Any]:
    if not store.configured(settings):
        return {"storage":"unavailable","memory":[],"research_kb":[],"scheduled_tasks":[]}
    memory=await store.request(settings,"GET","v11_memory_facts",params={"user_id":f"eq.{user_id}","select":"id,key,value,status,valid_from,valid_to,supersedes,updated_at","limit":"200"}) or []
    kb=await store.request(settings,"GET","v11_research_kb",params={"user_id":f"eq.{user_id}","select":"id,title,query,created_at","limit":"100"}) or []
    tasks=await store.request(settings,"GET","v11_scheduled_tasks",params={"user_id":f"eq.{user_id}","select":"id,title,run_at,cron,status,created_at","limit":"100"}) or []
    return {"storage":"supabase","memory":memory,"research_kb":kb,"scheduled_tasks":tasks,"controls":["export","delete","retention"]}

RETENTION_DEFAULTS={"chats_days":365,"audit_logs_days":180,"error_logs_days":90,"generated_artifacts_days":30,"temporary_ocr_days":1,"temporary_media_days":1}
