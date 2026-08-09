from __future__ import annotations
import asyncio, re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
from app.config import Settings
from app.services.research import search_web

_TRUST = (".gov", ".edu", ".ac.", "who.int", "worldbank.org", "oecd.org", "reuters.com", "apnews.com", "nature.com")

@dataclass
class ResearchBundle:
    query: str
    subqueries: list[str]
    sources: list[dict[str, Any]]
    conflicts: list[str]
    context: str = ""

def decompose_query(query: str, max_parts: int = 5) -> list[str]:
    clean = " ".join(str(query or "").split())
    if not clean:
        return []
    parts = [clean]
    for chunk in re.split(r"\b(?:and|vs|versus|aur)\b|[,;]", clean, flags=re.I):
        chunk = chunk.strip(" ,.;:-")
        if len(chunk) >= 8 and chunk.casefold() != clean.casefold() and chunk not in parts:
            parts.append(chunk)
    for probe in (f"{clean} official source", f"{clean} latest evidence", f"{clean} criticism counter evidence"):
        if probe not in parts:
            parts.append(probe)
    return parts[:max(1, min(5, max_parts))]

def _key(row: dict[str, Any]) -> str:
    try:
        u = urlparse(str(row.get("url") or ""))
        return f"{u.netloc.lower()}{u.path.rstrip('/')}"
    except Exception:
        return str(row.get("title") or "").casefold()

def deduplicate_sources(rows):
    seen, out = set(), []
    for row in rows:
        key = _key(row)
        if key and key not in seen:
            seen.add(key)
            out.append(row)
    return out

def source_rank(row):
    url = str(row.get("url") or "").casefold()
    content = str(row.get("content") or "")
    score = 3.0 if any(x in url for x in _TRUST) else 0.0
    score += min(2.0, len(content) / 2500.0)
    if row.get("published_date"):
        score += 1.0
    if str(row.get("source_type") or "").lower() in {"official", "primary", "government"}:
        score += 2.5
    return score

def rank_sources(rows, limit=14):
    return sorted(rows, key=source_rank, reverse=True)[:max(1, min(20, int(limit)))]

def detect_conflicts(rows):
    by_entity = {}
    for row in rows:
        entity = str(row.get("entity") or row.get("title") or "general").casefold()
        text = f"{row.get('title') or ''} {row.get('content') or ''}"
        values = set(re.findall(r"\b(?:19|20)\d{2}\b|\b\d+(?:\.\d+)?%\b", text))
        if values:
            by_entity.setdefault(entity, set()).update(values)
    out = []
    for entity, values in by_entity.items():
        if len(values) >= 3:
            out.append(f"Potentially conflicting/time-varying values for {entity}: {', '.join(sorted(values)[:8])}")
    return out[:8]

def build_context(bundle: ResearchBundle) -> str:
    lines = [
        "DEEP RESEARCH V2 EVIDENCE PACK",
        "Use only the evidence below for factual claims.",
        "Cite factual claims with source IDs exactly like [S1], [S2].",
        "If sources disagree, explain the disagreement and prefer primary/official/current evidence.",
        "Never invent citations.",
        "",
        "SUBQUERIES:",
        *[f"- {q}" for q in bundle.subqueries],
    ]
    if bundle.conflicts:
        lines += ["", "CONFLICT SIGNALS:", *[f"- {c}" for c in bundle.conflicts]]
    lines += ["", "SOURCES:"]
    for i, s in enumerate(bundle.sources, 1):
        lines.append(
            f"[S{i}] TITLE: {s.get('title') or 'Source'}\n"
            f"URL: {s.get('url') or ''}\n"
            f"DATE: {s.get('published_date') or 'not provided'}\n"
            f"TYPE: {s.get('source_type') or 'other'}\n"
            f"CONTENT: {str(s.get('content') or '')[:5000]}"
        )
    return "\n\n".join(lines)

async def build_research_bundle(query: str, settings: Settings, *, as_of: str | None = None, max_sources: int = 14):
    subqueries = decompose_query(query)
    async def run(q):
        try:
            rows, _ = await search_web(q, settings, 6, require_current=True, as_of=as_of)
            return rows
        except Exception:
            return []
    groups = await asyncio.gather(*(run(q) for q in subqueries))
    merged = [row for group in groups for row in group]
    sources = rank_sources(deduplicate_sources(merged), max_sources)
    bundle = ResearchBundle(query=query, subqueries=subqueries, sources=sources, conflicts=detect_conflicts(sources))
    bundle.context = build_context(bundle)
    return bundle

def verify_citations(answer: str, sources: list[dict[str, Any]]):
    source_map = {i: f"{s.get('title') or ''} {s.get('content') or ''}".casefold() for i, s in enumerate(sources, 1)}
    checked, supported = [], 0
    for claim in re.split(r"(?<=[.!?])\s+", str(answer or "")):
        ids = {int(x) for x in re.findall(r"\[S?(\d+)\]", claim)}
        if not ids:
            continue
        tokens = {t for t in re.findall(r"[a-zA-Z0-9]{4,}", claim.casefold()) if t not in {"this","that","with","from","source"}}
        evidence = " ".join(source_map.get(i, "") for i in ids)
        overlap = len([t for t in tokens if t in evidence]) / max(1, len(tokens))
        ok = bool(evidence) and overlap >= 0.22
        supported += int(ok)
        checked.append({"claim": claim[:500], "source_ids": sorted(ids), "supported": ok, "lexical_support": round(overlap, 3)})
    return {
        "claims_checked": len(checked),
        "claims_supported": supported,
        "support_rate": round(supported / max(1, len(checked)), 3) if checked else None,
        "details": checked[:50],
    }
