from __future__ import annotations
from app.services.context import ContextStats, compact_messages as base_compact

def _clip(v: str, limit=300):
    s=" ".join(str(v or "").split())
    if len(s)<=limit: return s
    return s[:215]+" ... "+s[-80:]

def compact_messages_v7(messages,*,max_chars,max_single_message_chars):
    if len(messages)<=10:
        return base_compact(messages,max_chars=max_chars,max_single_message_chars=max_single_message_chars)
    older=messages[:-8]; recent=messages[-8:]
    digest=["COMPRESSED OLDER CHAT (extractive; do not invent omitted details):"]
    for m in older[-16:]:
        digest.append(f"- {m.get('role','user')}: {_clip(m.get('content',''))}")
    candidate=[{"role":"system","content":"\n".join(digest)},*recent]
    compacted,stats=base_compact(candidate,max_chars=max_chars,max_single_message_chars=max_single_message_chars)
    return compacted,ContextStats(
        original_chars=sum(len(str(x.get("content") or "")) for x in messages),
        used_chars=sum(len(str(x.get("content") or "")) for x in compacted),
        omitted_messages=max(1,len(older)),
        truncated_messages=stats.truncated_messages,
    )
