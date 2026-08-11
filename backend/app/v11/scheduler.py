from __future__ import annotations
import re, uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from app.v11 import store

def now_iso()->str:return datetime.now(timezone.utc).isoformat()

def next_run_from_cron(cron: str, base: datetime|None=None)->str|None:
    base=(base or datetime.now(timezone.utc)).replace(second=0,microsecond=0)
    value=(cron or "").strip()
    m=re.fullmatch(r"\*/(\d{1,3}) \* \* \* \*",value)
    if m:
        minutes=max(1,min(1440,int(m.group(1))))
        return (base+timedelta(minutes=minutes)).isoformat()
    m=re.fullmatch(r"(\d{1,2}) (\d{1,2}) \* \* \*",value)
    if m:
        minute,hour=int(m.group(1)),int(m.group(2))
        if 0<=minute<60 and 0<=hour<24:
            candidate=base.replace(hour=hour,minute=minute)
            if candidate<=base:candidate+=timedelta(days=1)
            return candidate.isoformat()
    return None

async def create_task(settings, *, user_id: str, title: str, prompt: str, run_at: str|None=None, cron: str|None=None)->dict[str,Any]:
    effective_run=run_at or next_run_from_cron(cron or "")
    if not effective_run: raise ValueError("Unsupported cron. Use */N * * * * or M H * * *.")
    row={"id":str(uuid.uuid4()),"user_id":user_id,"title":title[:200],"prompt":prompt[:12000],"run_at":effective_run,"cron":cron,"status":"scheduled","last_run_at":None,"created_at":now_iso()}
    if store.configured(settings):
        rows=await store.request(settings,"POST","v11_scheduled_tasks",json_body=row)
        if isinstance(rows,list) and rows:return rows[0]
    return row

async def due_tasks(settings, limit: int=20)->list[dict[str,Any]]:
    if not store.configured(settings):return []
    return await store.request(settings,"GET","v11_scheduled_tasks",params={"status":"eq.scheduled","run_at":f"lte.{now_iso()}","select":"*","limit":str(max(1,min(100,limit)))}) or []

async def scheduler_tick(settings, executor)->dict[str,Any]:
    rows=await due_tasks(settings); completed=0; errors=[]
    for row in rows:
        try:
            result=await executor(row)
            cron=str(row.get("cron") or "").strip()
            if cron:
                next_run=next_run_from_cron(cron)
                update={"status":"scheduled","run_at":next_run,"last_run_at":now_iso(),"result":result}
            else:
                update={"status":"completed","last_run_at":now_iso(),"result":result}
            await store.request(settings,"PATCH","v11_scheduled_tasks",params={"id":f"eq.{row['id']}"},json_body=update)
            completed+=1
        except Exception as exc:
            errors.append({"id":row.get("id"),"error":str(exc)[:500]})
            await store.request(settings,"PATCH","v11_scheduled_tasks",params={"id":f"eq.{row['id']}"},json_body={"status":"error","last_run_at":now_iso(),"result":{"error":str(exc)[:500]}})
    return {"checked":len(rows),"completed":completed,"errors":errors}

def runtime_note()->str:
    return "Persistent one-time and recurring tasks are supported. On free hosts that sleep, exact wake-up timing requires an external cron/always-on trigger."
