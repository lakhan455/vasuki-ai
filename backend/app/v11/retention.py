from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any
from app.v11 import store
from app.v11.operations import RETENTION_DEFAULTS

SCOPES={
    "chats":"chats_days",
    "audit_logs":"audit_logs_days",
    "error_logs":"error_logs_days",
    "generated_artifacts":"generated_artifacts_days",
    "temporary_ocr":"temporary_ocr_days",
    "temporary_media":"temporary_media_days",
}

async def policies(settings,user_id: str)->dict[str,int]:
    values={scope:int(RETENTION_DEFAULTS[key]) for scope,key in SCOPES.items()}
    if store.configured(settings):
        rows=await store.request(settings,"GET","v11_retention_policies",params={"or":f"(user_id.eq.{user_id},user_id.is.null)","select":"user_id,scope,retention_days,updated_at","order":"updated_at.asc"}) or []
        for row in rows:
            scope=str(row.get("scope") or "")
            if scope in values: values[scope]=int(row.get("retention_days") or 0)
    return values

async def set_policy(settings,user_id: str,scope: str,days: int)->dict[str,Any]:
    if scope not in SCOPES: raise ValueError("Unknown retention scope.")
    days=max(0,min(3650,int(days)))
    row={"user_id":user_id,"scope":scope,"retention_days":days,"updated_at":datetime.now(timezone.utc).isoformat()}
    if store.configured(settings):
        existing=await store.request(settings,"GET","v11_retention_policies",params={"user_id":f"eq.{user_id}","scope":f"eq.{scope}","select":"id"}) or []
        if existing:
            rows=await store.request(settings,"PATCH","v11_retention_policies",params={"id":f"eq.{existing[0]['id']}"},json_body=row)
        else:
            rows=await store.request(settings,"POST","v11_retention_policies",json_body=row)
        if isinstance(rows,list) and rows:return rows[0]
    return row

async def cleanup_v11_tables(settings)->dict[str,Any]:
    if not store.configured(settings):return {"configured":False,"deleted":{}}
    now=datetime.now(timezone.utc); deleted={}
    targets=[
        ("v11_tool_permissions","created_at",1),
        ("v11_provider_quality","created_at",365),
        ("v11_reliability_samples","created_at",90),
        ("v11_abuse_events","created_at",90),
    ]
    for table,column,days in targets:
        cutoff=(now-timedelta(days=days)).isoformat()
        try:
            rows=await store.request(settings,"DELETE",table,params={column:f"lt.{cutoff}","select":"id"}) or []
            deleted[table]=len(rows) if isinstance(rows,list) else 0
        except Exception as exc:
            deleted[table]={"error":str(exc)[:200]}
    return {"configured":True,"deleted":deleted}
