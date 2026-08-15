from __future__ import annotations
import asyncio, hashlib, time
from collections.abc import AsyncIterator
from typing import Any
from app.config import Settings
from app.services import chat as legacy
from app.services.cache_v7 import RESPONSE_CACHE, norm
from app.services.chat_v4 import safe_error
from app.services.chat_v5 import _stream_provider_segment, build_resume_messages
from app.services.router_v7 import base_candidates, classify_route, configured_provider, last_user_query
from app.services.telemetry_v7 import available, attempt, success, failure, record
from app.services.quality_v9 import rank_for_task

def _chunks(s,size=80): return [s[i:i+size] for i in range(0,len(s),size)]

def _cache_key(messages,tier):
    if len(messages)>2: return None
    q=last_user_query(messages).strip()
    if not q or len(q)>500: return None
    low=q.casefold()
    if any(x in low for x in ("my ","mere ","mera ","mujhe ","remember","yaad","today","latest","current","abhi")): return None
    return hashlib.sha256(f"{tier}|{norm(q)}".encode()).hexdigest()

def _provider_family(name: str | None) -> str:
    value = str(name or "").strip().casefold()
    if value.startswith("cache:"):
        value = value.split(":", 1)[1]
    if value in {"groq", "groq_fast"}:
        return "groq"
    return value


def _reaction_priority(
    names: list[str],
    tier: str,
) -> list[str]:
    ordered = list(dict.fromkeys(names))

    # The small Groq route exists specifically for low-latency
    # first-token responses.
    if tier == "fast" and "groq_fast" in ordered:
        ordered.remove("groq_fast")
        ordered.insert(0, "groq_fast")

    # Gemini currently uses a non-streaming adapter in this
    # router, therefore keep it as a fallback when streaming
    # alternatives exist.
    if "gemini" in ordered and len(ordered) > 1:
        ordered.remove("gemini")
        ordered.append("gemini")

    return ordered


async def route_chat_stream_v7(
    provider: str,
    messages: list[dict[str,Any]],
    settings: Settings,
    web_context: str="",
    *,
    require_current=False,
    as_of=None,
    cache_bypass: bool=False,
    exclude_provider: str | None=None,
)->AsyncIterator[dict[str,str]]:
    started=time.perf_counter()
    d=classify_route(messages,require_current=require_current)
    q=last_user_query(messages)
    max_attempts=max(1,min(7,int(getattr(settings,"max_provider_attempts",7))))
    excluded_family=_provider_family(exclude_provider)
    base=[n for n in base_candidates(d,provider) if configured_provider(n,settings) and legacy._provider_is_available(n)]
    healthy=[n for n in base if available(n)]
    alternatives=[n for n in healthy if not excluded_family or _provider_family(n)!=excluded_family]
    candidates=_reaction_priority(
        rank_for_task(alternatives,d.task_type),
        d.tier,
    )[:max_attempts]
    if not candidates:
        alternatives=[n for n in base if not excluded_family or _provider_family(n)!=excluded_family]
        candidates=_reaction_priority(
            rank_for_task(alternatives,d.task_type),
            d.tier,
        )[:max_attempts]
    if not candidates:
        candidates=_reaction_priority(
            rank_for_task(healthy or base,d.task_type),
            d.tier,
        )[:max_attempts]
    if not candidates: raise RuntimeError("No healthy AI provider is currently available.")

    ckey=None
    if (not cache_bypass) and getattr(settings,"response_cache_enabled",True) and not require_current and not web_context.strip() and d.task_type in {"simple","general"}:
        ckey=_cache_key(messages,d.tier)
        if ckey:
            hit=RESPONSE_CACHE.get(ckey)
            if hit:
                answer,p=hit
                yield {"type":"provider","provider":f"cache:{p}"}
                for chunk in _chunks(answer):
                    yield {"type":"token","token":chunk}; await asyncio.sleep(0)
                record({"task_type":d.task_type,"tier":d.tier,"language":d.language,"provider":f"cache:{p}","attempts":0,"latency_ms":round((time.perf_counter()-started)*1000),"cache_hit":True})
                return

    complete=""; errors=[]; first_token_ms=None; attempts=0; final_provider=""
    for name in candidates:
        attempts+=1; attempt(name); pstarted=time.perf_counter()
        working=build_resume_messages(messages,complete); emitted=False
        yield {"type":"diagnostic","provider":name,"status":f"trying:{d.task_type}:{d.tier}"}
        try:
            if name=="gemini":
                answer=await asyncio.wait_for(
                    legacy.chat_gemini(working,settings,web_context,require_current=require_current,as_of=as_of,temperature=0.0 if require_current else 0.2),
                    timeout=float(getattr(settings,"large_provider_timeout_seconds",45)),
                )
                if not answer.strip(): raise RuntimeError("Gemini returned an empty answer")
                final_provider=name; emitted=True
                first_token_ms=first_token_ms or round((time.perf_counter()-started)*1000)
                yield {"type":"provider","provider":name}
                for chunk in _chunks(answer):
                    complete+=chunk; yield {"type":"token","token":chunk}; await asyncio.sleep(0)
            else:
                max_cont=max(0,min(4,int(getattr(settings,"max_continuations",2))))
                for idx in range(max_cont+1):
                    segment=""; finish=""
                    it=_stream_provider_segment(name=name,messages=working,settings=settings,web_context=web_context,require_current=require_current,as_of=as_of,large_request=d.tier=="strong")
                    try:
                        ev=await asyncio.wait_for(anext(it),timeout=max(
                            1.25,
                            float(
                                getattr(
                                    settings,
                                    "first_token_timeout_seconds",
                                    1.6,
                                )
                            ),
                        ))
                        pending=[ev]
                        while pending:
                            e=pending.pop(0)
                            if e.get("type")=="token":
                                token=e.get("token","")
                                if token:
                                    if not emitted:
                                        emitted=True; final_provider=name
                                        first_token_ms=first_token_ms or round((time.perf_counter()-started)*1000)
                                        yield {"type":"provider","provider":name}
                                    segment+=token; complete+=token; yield {"type":"token","token":token}
                            elif e.get("type")=="finish": finish=e.get("reason","")
                        async for e in it:
                            if e.get("type")=="token":
                                token=e.get("token","")
                                if token:
                                    if not emitted:
                                        emitted=True; final_provider=name
                                        first_token_ms=first_token_ms or round((time.perf_counter()-started)*1000)
                                        yield {"type":"provider","provider":name}
                                    segment+=token; complete+=token; yield {"type":"token","token":token}
                            elif e.get("type")=="finish": finish=e.get("reason","")
                    finally:
                        try: await it.aclose()
                        except Exception: pass
                    if not segment: raise RuntimeError("Provider returned an empty stream")
                    if legacy._is_length_finish(finish) and idx<max_cont:
                        working.extend([{"role":"assistant","content":segment},{"role":"user","content":legacy._continuation_instruction()}])
                        continue
                    break

            success(name,round((time.perf_counter()-pstarted)*1000)); legacy._clear_provider_failure(name)
            if ckey and complete.strip(): RESPONSE_CACHE.set(ckey,(complete.strip(),name),int(getattr(settings,"response_cache_ttl_seconds",900)))
            record({
                "task_type":d.task_type,"difficulty":d.difficulty,"tier":d.tier,"language":d.language,
                "message_chars":len(q),"estimated_input_tokens":max(1,sum(len(str(m.get("content") or "")) for m in messages)//4),
                "estimated_output_tokens":max(1,len(complete)//4),"provider":final_provider or name,
                "attempts":attempts,"first_token_ms":first_token_ms,
                "latency_ms":round((time.perf_counter()-started)*1000),"cache_hit":False,
            })
            yield {"type":"diagnostic","provider":name,"status":"completed"}
            return
        except Exception as exc:
            failure(name,exc); legacy._mark_provider_failure(name,exc,settings)
            clean=safe_error(exc); errors.append(f"{name}: {clean}")
            yield {"type":"diagnostic","provider":name,"status":"failed","error":clean}
            if emitted: yield {"type":"diagnostic","provider":name,"status":"resuming_same_tier"}

    if complete.strip(): return
    record({"task_type":d.task_type,"tier":d.tier,"language":d.language,"provider":final_provider,"attempts":attempts,"latency_ms":round((time.perf_counter()-started)*1000),"error":" | ".join(errors[-3:])})
    raise RuntimeError("All selected same-tier providers failed. "+" | ".join(errors[-3:]))
