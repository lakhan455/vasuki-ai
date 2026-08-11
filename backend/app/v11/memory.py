from __future__ import annotations
import re, uuid
from datetime import datetime, timezone
from typing import Any
from app.v11 import store

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def normalize_key(text: str) -> str:
    text=re.sub(r"\s+"," ",(text or "").strip().casefold())
    text=re.sub(r"[^a-z0-9\u0900-\u097f _-]","",text)
    return text[:240]

def conflict_score(a: str,b: str) -> float:
    ta=set(normalize_key(a).split()); tb=set(normalize_key(b).split())
    if not ta or not tb: return 0.0
    common=len(ta&tb)/max(1,min(len(ta),len(tb)))
    neg_a=bool(re.search(r"\b(no|not|never|inactive|false|nahi|nhi)\b",a,re.I))
    neg_b=bool(re.search(r"\b(no|not|never|inactive|false|nahi|nhi)\b",b,re.I))
    return min(1.0,common+(0.35 if neg_a!=neg_b else 0.0))

async def upsert_temporal_memory(settings, *, user_id: str, project_id: str | None, key: str, value: str, source: str="user", valid_from: str | None=None) -> dict[str, Any]:
    key_norm=normalize_key(key)
    now=_now()
    existing=[]
    if store.configured(settings):
        existing=await store.request(settings,"GET","v11_memory_facts",params={"user_id":f"eq.{user_id}","key_norm":f"eq.{key_norm}","status":"eq.active","select":"*"}) or []
    supersedes=None
    for row in existing:
        if str(row.get("value") or "").strip()!=value.strip():
            supersedes=row.get("id")
            if store.configured(settings):
                await store.request(settings,"PATCH","v11_memory_facts",params={"id":f"eq.{row['id']}","user_id":f"eq.{user_id}"},json_body={"status":"superseded","valid_to":now,"updated_at":now})
    record={"id":str(uuid.uuid4()),"user_id":user_id,"project_id":project_id,"key":key[:500],"key_norm":key_norm,"value":value[:12000],"source":source[:120],"status":"active","valid_from":valid_from or now,"valid_to":None,"supersedes":supersedes,"updated_at":now}
    if store.configured(settings):
        rows=await store.request(settings,"POST","v11_memory_facts",json_body=record)
        if isinstance(rows,list) and rows:return rows[0]
    return record

async def active_memory(settings, *, user_id: str, project_id: str | None=None, limit: int=100) -> list[dict[str,Any]]:
    if not store.configured(settings): return []
    params={"user_id":f"eq.{user_id}","status":"eq.active","select":"*","order":"updated_at.desc","limit":str(max(1,min(500,limit)))}
    if project_id: params["project_id"]=f"eq.{project_id}"
    return await store.request(settings,"GET","v11_memory_facts",params=params) or []

def resolve_conflicts(rows: list[dict[str,Any]]) -> list[dict[str,Any]]:
    newest={}
    for row in sorted(rows,key=lambda x:str(x.get("updated_at") or ""),reverse=True):
        key=str(row.get("key_norm") or normalize_key(str(row.get("key") or "")))
        if key and key not in newest and str(row.get("status") or "active")=="active":
            newest[key]=row
    return list(newest.values())
