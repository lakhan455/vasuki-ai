from __future__ import annotations
from typing import Any
from fastapi import Depends
import app.main as legacy
import app.main_v5 as v5
import app.main_v6 as v6
from app.auth import AuthUser, get_current_user
from app.services.cache_v7 import RESPONSE_CACHE, WEB_CACHE, cached_web_search
from app.services.chat_v7 import route_chat_stream_v7
from app.services.context_v7 import compact_messages_v7
from app.services.telemetry_v7 import snapshot, recent

app=v6.app
settings=v6.settings
v5.route_chat_stream_v5=route_chat_stream_v7
legacy.compact_messages=compact_messages_v7

_original_search_web=legacy.search_web
async def _cached_search_web(query,app_settings,max_results=10,*,require_current=False,as_of=None):
    return await cached_web_search(_original_search_web,query,app_settings,max_results,require_current=require_current,as_of=as_of)
legacy.search_web=_cached_search_web

@app.get("/api/diagnostics/optimization-v7")
async def optimization_v7(current_user: AuthUser=Depends(get_current_user))->dict[str,Any]:
    return {
        "ok":True,"router_version":"v7","user_id_suffix":current_user.id[-6:],
        "provider_health":snapshot(),"recent_requests":recent(50),
        "cache":{"responses":RESPONSE_CACHE.snapshot(),"web":WEB_CACHE.snapshot()},
        "settings":{"max_provider_attempts":int(getattr(settings,"max_provider_attempts",3)),
                    "context_strategy":"extractive_digest_plus_last_8"},
    }

@app.get("/health/extended")
async def health_extended():
    configured=sum(bool(x) for x in (
        settings.groq_api_key,settings.sambanova_api_key,settings.cerebras_api_key,
        settings.google_gemini_api,settings.openrouter_api,settings.mistral_ai_api))
    return {"ok":True,"service":settings.app_name,"router":"v7","providers_configured":configured,
            "supabase_configured":bool(settings.supabase_url),"truth_guard":True,"rag":True}
