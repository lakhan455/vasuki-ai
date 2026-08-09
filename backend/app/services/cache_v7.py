from __future__ import annotations
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

@dataclass
class Entry:
    expires: float
    value: Any

class TTLCache:
    def __init__(self,max_items=300):
        self.max_items=max_items; self.items=OrderedDict(); self.hits=0; self.misses=0
    def get(self,key):
        e=self.items.get(key)
        if not e: self.misses+=1; return None
        if e.expires<=time.monotonic(): self.items.pop(key,None); self.misses+=1; return None
        self.items.move_to_end(key); self.hits+=1; return e.value
    def set(self,key,value,ttl):
        self.items[key]=Entry(time.monotonic()+max(1,int(ttl)),value); self.items.move_to_end(key)
        while len(self.items)>self.max_items: self.items.popitem(last=False)
    def snapshot(self): return {"items":len(self.items),"hits":self.hits,"misses":self.misses}

RESPONSE_CACHE=TTLCache()
WEB_CACHE=TTLCache()

def norm(s: str)->str: return " ".join(str(s or "").casefold().split())[:6000]

async def cached_web_search(original: Callable[...,Awaitable[tuple[list[dict],str]]],query,settings,max_results=10,*,require_current=False,as_of=None):
    ttl=int(getattr(settings,"web_cache_current_ttl_seconds" if require_current else "web_cache_stable_ttl_seconds",60 if require_current else 600))
    key=f"{int(require_current)}|{as_of or ''}|{max_results}|{norm(query)}"
    hit=WEB_CACHE.get(key)
    if hit is not None:
        sources,provider=hit
        return sources,f"cache:{provider}"
    result=await original(query,settings,max_results,require_current=require_current,as_of=as_of)
    if result[0]: WEB_CACHE.set(key,result,ttl)
    return result
