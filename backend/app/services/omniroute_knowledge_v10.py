from __future__ import annotations

import gzip
import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "omniroute_v10_knowledge.json.gz"
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:+-]{1,48}")
_STOP = {
    "the","and","for","with","that","this","from","are","was","were","have","has","had",
    "you","your","into","not","can","will","use","using","used","how","what","when","where",
    "why","which","its","their","then","than","also","all","any","per","via","one","two",
    "mein","me","mere","mera","mujhe","kya","kaise","kese","hai","he","ko","ka","ki","ke",
}
_OMNI_HINTS = (
    "omniroute","auto/coding","auto/reasoning","auto/fast","auto/cheap","auto/offline",
    "auto/smart","auto combo","provider routing","provider fallback","circuit breaker",
    "connection cooldown","model lockout","quota routing","cost routing","mcp","a2a",
    "compression engine","rtk compression","provider combo","routing strategy",
    "provider catalog","openai compatible gateway","x-omniroute",
)

def _tokens(value: str) -> list[str]:
    return [
        token.casefold()
        for token in _TOKEN_RE.findall(value or "")
        if len(token) >= 2 and token.casefold() not in _STOP
    ]

@lru_cache(maxsize=1)
def _corpus() -> dict[str, Any]:
    if not _DATA_PATH.exists():
        return {"meta": {"missing": True}, "chunks": []}
    with gzip.open(_DATA_PATH, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        return {"meta": {"invalid": True}, "chunks": []}
    return payload

def corpus_info() -> dict[str, Any]:
    payload = _corpus()
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    return {
        **meta,
        "available": bool(payload.get("chunks")),
        "path": str(_DATA_PATH.name),
    }

def is_omniroute_query(query: str) -> bool:
    low = (query or "").casefold()
    if any(hint in low for hint in _OMNI_HINTS):
        return True
    tokens = set(_tokens(low))
    domain = {
        "provider","routing","router","fallback","quota","latency","cost","model","models",
        "gateway","combo","compression","guardrail","mcp","a2a","circuit","cooldown","lockout",
    }
    return len(tokens & domain) >= 3

def search_omniroute_knowledge(query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    q_tokens = _tokens(query)
    if not q_tokens:
        return []
    q_counts: dict[str, int] = {}
    for token in q_tokens:
        q_counts[token] = q_counts.get(token, 0) + 1

    chunks = _corpus().get("chunks") or []
    scored: list[tuple[float, dict[str, Any]]] = []
    phrase = " ".join(q_tokens[:6])

    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        path = str(chunk.get("path") or "")
        title = str(chunk.get("title") or "")
        section = str(chunk.get("section") or "")
        text = str(chunk.get("text") or "")
        hay = f"{path}\n{title}\n{section}\n{text}".casefold()
        score = 0.0

        for token, qtf in q_counts.items():
            count = hay.count(token)
            if not count:
                continue
            tf = 1.0 + math.log1p(min(count, 12))
            score += tf * (1.0 + min(qtf, 3) * 0.12)
            if token in path.casefold():
                score += 2.4
            if token in section.casefold():
                score += 1.8
            if token in title.casefold():
                score += 1.2

        if phrase and phrase in hay:
            score += 5.0

        # Prefer canonical docs over implementation details for user-facing explanations,
        # while keeping source chunks searchable for exact implementation questions.
        if path.startswith("docs/"):
            score *= 1.12
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for score, chunk in scored:
        key = (str(chunk.get("path") or ""), str(chunk.get("section") or ""))
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "path": key[0],
            "section": key[1],
            "title": str(chunk.get("title") or ""),
            "text": str(chunk.get("text") or ""),
            "score": round(score, 3),
        })
        if len(results) >= max(1, min(limit, 12)):
            break
    return results

def omniroute_context(query: str, *, limit: int = 4, max_chars: int = 9000) -> str:
    if not is_omniroute_query(query):
        return ""
    results = search_omniroute_knowledge(query, limit=limit)
    if not results:
        return ""

    parts = [
        "VASUKI OMNIROUTE KNOWLEDGE PACK (source-derived, use only when relevant):",
        "Treat this as technical reference context. Preserve source distinctions and do not invent unsupported OmniRoute behavior.",
    ]
    used = sum(len(part) for part in parts)

    for item in results:
        header = f"[OmniRoute source: {item['path']} — {item['section']}]"
        text = item["text"].strip()
        remaining = max_chars - used - len(header) - 4
        if remaining <= 200:
            break
        if len(text) > remaining:
            text = text[:remaining].rsplit(" ", 1)[0] + "…"
        parts.extend([header, text])
        used += len(header) + len(text) + 4

    return "\n\n".join(parts)
