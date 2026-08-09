from __future__ import annotations
import time, re
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Any

@dataclass
class ProviderHealth:
    attempts: int=0
    successes: int=0
    failures: int=0
    consecutive_failures: int=0
    ewma_latency_ms: float|None=None
    last_error: str=""
    blocked_until: float=0.0
    quota_blocked_until: float=0.0

_LOCK=Lock()
_PROVIDERS: dict[str,ProviderHealth]={}
_REQUESTS: deque[dict[str,Any]]=deque(maxlen=500)
_SECRET=(re.compile(r"(?i)\b(?:bearer|apikey|api[_ -]?key|secret|token)\s*[:=]\s*\S+"),)

def _safe(x: object) -> str:
    s=str(x or "")[:500]
    for p in _SECRET: s=p.sub("[redacted]",s)
    return s

def _get(name: str) -> ProviderHealth:
    with _LOCK: return _PROVIDERS.setdefault(name,ProviderHealth())

def available(name: str) -> bool:
    h=_get(name); now=time.monotonic()
    return now>=h.blocked_until and now>=h.quota_blocked_until

def rank(names: list[str]) -> list[str]:
    scored=[]
    for i,name in enumerate(names):
        h=_get(name)
        rate=1.0 if not h.attempts else h.successes/h.attempts
        score=i+(h.ewma_latency_ms or 0)/4000+h.consecutive_failures*1.7+(1-rate)*2+(0 if available(name) else 1000)
        scored.append((score,name))
    return [n for _,n in sorted(scored)]

def attempt(name: str) -> None:
    with _LOCK: _PROVIDERS.setdefault(name,ProviderHealth()).attempts+=1

def success(name: str, ms: int) -> None:
    with _LOCK:
        h=_PROVIDERS.setdefault(name,ProviderHealth())
        h.successes+=1; h.consecutive_failures=0; h.last_error=""
        h.ewma_latency_ms=float(ms) if h.ewma_latency_ms is None else h.ewma_latency_ms*.72+ms*.28
        h.blocked_until=0; h.quota_blocked_until=0

def failure(name: str, error: object) -> None:
    msg=_safe(error); q=msg.casefold(); now=time.monotonic()
    with _LOCK:
        h=_PROVIDERS.setdefault(name,ProviderHealth())
        h.failures+=1; h.consecutive_failures+=1; h.last_error=msg
        if any(x in q for x in ("429","quota","rate limit","too many requests")): h.quota_blocked_until=now+900
        elif any(x in q for x in ("401","402","403","payment required","unauthorized")): h.blocked_until=now+1800
        elif "timeout" in q or "timed out" in q: h.blocked_until=now+90
        elif h.consecutive_failures>=3: h.blocked_until=now+300

def record(row: dict[str,Any]) -> None:
    row=dict(row); row["time"]=int(time.time())
    if "error" in row: row["error"]=_safe(row["error"])
    with _LOCK: _REQUESTS.append(row)

def snapshot() -> dict[str,Any]:
    now=time.monotonic()
    with _LOCK:
        return {name:{
            "attempts":h.attempts,"successes":h.successes,"failures":h.failures,
            "success_rate":round(1.0 if not h.attempts else h.successes/h.attempts,3),
            "ewma_latency_ms":None if h.ewma_latency_ms is None else round(h.ewma_latency_ms,1),
            "last_error":h.last_error,
            "cooldown_remaining_seconds":max(0,round(max(h.blocked_until,h.quota_blocked_until)-now)),
            "quota_limited":h.quota_blocked_until>now,
        } for name,h in _PROVIDERS.items()}

def recent(limit: int=50) -> list[dict[str,Any]]:
    with _LOCK: return list(_REQUESTS)[-max(1,min(limit,200)):]
