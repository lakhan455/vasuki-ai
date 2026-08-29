from __future__ import annotations

import asyncio
import re
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.services.knowledge import _upsert_verified
from app.services.research import INDIA_STATES


@dataclass(frozen=True, slots=True)
class LiveTopic:
    id: str
    question: str
    aliases: tuple[str, ...]
    require_all_india_state_entities: bool = False


DEFAULT_TOPICS: tuple[LiveTopic, ...] = (
    LiveTopic(
        id="india-state-chief-ministers",
        question=(
            "As of today, give the complete current Chief Ministers of all 28 Indian states. "
            "Verify each state separately using the newest reliable evidence."
        ),
        aliases=(
            "all India state CM list",
            "India all CM list",
            "India chief ministers list",
            "bharat ke sabhi cm",
            "india ke saare cm",
            "ind ke saare cm ki list",
            "sabhi rajya ke cm",
        ),
        require_all_india_state_entities=True,
    ),
    LiveTopic(
        id="india-top-officeholders",
        question=(
            "As of today, list the current President, Vice President, Prime Minister, "
            "Home Minister, Finance Minister and External Affairs Minister of India."
        ),
        aliases=(
            "current India top office holders",
            "India president prime minister ministers current",
            "bharat ke vartaman rashtrapati pradhanmantri mantri",
        ),
    ),
    LiveTopic(
        id="india-government-updates",
        question=(
            "What are the newest major Government of India policy, law, rule, cabinet, "
            "appointment and PIB updates that materially changed in the last 7 days?"
        ),
        aliases=(
            "latest India government updates",
            "latest government rules India",
            "latest PIB cabinet policy India",
        ),
    ),
    LiveTopic(
        id="ai-model-releases",
        question=(
            "What are the newest major AI model, API and product releases from leading AI labs "
            "and platforms, with current model/version names and dates?"
        ),
        aliases=(
            "latest AI models",
            "latest AI releases",
            "new AI model updates",
            "latest OpenAI Google Meta Mistral AI updates",
        ),
    ),
    LiveTopic(
        id="software-platform-releases",
        question=(
            "What are the newest stable version and major security/release updates for Windows, "
            "Android, iOS, Python, Node.js and Next.js?"
        ),
        aliases=(
            "latest software versions",
            "latest Windows Android iOS Python Node Next.js",
            "current software release versions",
        ),
    ),
    LiveTopic(
        id="india-current-affairs",
        question=(
            "Summarize the most important verified India current-affairs developments from the "
            "last 24 hours, prioritizing official and high-quality sources."
        ),
        aliases=("India latest news", "India current affairs today", "latest India developments"),
    ),
    LiveTopic(
        id="world-current-affairs",
        question=(
            "Summarize the most important verified world developments from the last 24 hours, "
            "prioritizing primary sources and highly reputable reporting."
        ),
        aliases=("world latest news", "world current affairs today", "latest global developments"),
    ),
    LiveTopic(
        id="india-markets-rbi",
        question=(
            "What are the latest important RBI policy-rate, banking-regulation and major Indian "
            "financial-market status updates that are currently valid?"
        ),
        aliases=("latest RBI rate", "India market latest", "RBI banking current updates"),
    ),
)

_PRIVATE = (
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"(?<!\d)(?:\+?91[-\s]?)?[6-9]\d{9}(?!\d)"),
    re.compile(r"\b(?:password|passwd|otp|aadhaar|pan card|api[_ -]?key|secret|access[_ -]?token)\b", re.I),
)

_pending: deque[str] = deque()
_pending_seen: set[str] = set()
_cursor = 0
_state: dict[str, Any] = {
    "running": False,
    "last_cycle_started_at": None,
    "last_cycle_finished_at": None,
    "last_success_at": None,
    "cycles": 0,
    "refresh_successes": 0,
    "refresh_failures": 0,
    "last_error": "",
    "topics": {},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _search_ready(settings: Any) -> bool:
    tavily = bool(str(getattr(settings, "tavily_api_key", "") or "").strip())
    exa = bool(str(getattr(settings, "exa_api", "") or "").strip())
    omni = bool(
        getattr(settings, "omniroute_enabled", False)
        and getattr(settings, "omniroute_search_enabled", False)
        and str(getattr(settings, "omniroute_base_url", "") or "").strip()
    )
    return tavily or exa or omni


def _storage_ready(settings: Any) -> bool:
    return bool(getattr(settings, "global_learning_configured", False))


def _safe_public_query(query: str) -> bool:
    value = str(query or "").strip()
    if len(value) < 3 or len(value) > 700:
        return False
    if any(pattern.search(value) for pattern in _PRIVATE):
        return False
    return True


def observe_current_query(query: str) -> bool:
    """Queue a public freshness-sensitive query for later background refresh."""
    value = re.sub(r"\s+", " ", str(query or "")).strip()
    if not _safe_public_query(value):
        return False
    key = value.casefold()
    if key in _pending_seen:
        return False
    max_pending = 64
    while len(_pending) >= max_pending:
        old = _pending.popleft()
        _pending_seen.discard(old.casefold())
    _pending.append(value)
    _pending_seen.add(key)
    return True


def _source_pack(sources: list[dict[str, Any]], max_chars: int = 28000) -> str:
    parts: list[str] = []
    used = 0
    for index, source in enumerate(sources, 1):
        block = (
            f"[{index}] ENTITY: {source.get('entity') or 'general'}\n"
            f"TYPE: {source.get('source_type') or 'other'}\n"
            f"TITLE: {source.get('title') or 'Source'}\n"
            f"URL: {source.get('url') or ''}\n"
            f"DATE: {source.get('published_date') or 'not provided'}\n"
            f"CONTENT:\n{str(source.get('content') or '')[:2200]}"
        )
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


def _unique_urls(sources: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in sources:
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        result.append(url)
        if len(result) >= 12:
            break
    return result


def _entity_coverage(sources: list[dict[str, Any]]) -> set[str]:
    return {
        str(item.get("entity") or "").strip().casefold()
        for item in sources
        if str(item.get("entity") or "").strip()
    }


def _topic_from_query(query: str) -> LiveTopic:
    clean = re.sub(r"\s+", " ", str(query or "")).strip()
    stable_id = sum((index + 1) * ord(ch) for index, ch in enumerate(clean.casefold()))
    return LiveTopic(
        id=f"adaptive-{stable_id:x}",
        question=clean,
        aliases=(clean,),
    )


async def refresh_topic(settings: Any, topic: LiveTopic) -> dict[str, Any]:
    started = time.perf_counter()
    as_of = datetime.now(timezone.utc).date().isoformat()

    import app.main as legacy

    max_results = max(4, min(16, int(getattr(settings, "v49_search_results_per_topic", 10))))
    sources, provider = await legacy.search_web(
        topic.question,
        settings,
        max_results,
        require_current=True,
        as_of=as_of,
    )

    min_sources = max(1, int(getattr(settings, "v49_min_sources", 2)))
    if len(sources) < min_sources:
        raise RuntimeError(
            f"Not enough current evidence for {topic.id}: {len(sources)} source(s)."
        )

    if topic.require_all_india_state_entities:
        found = _entity_coverage(sources)
        missing = [state for state in INDIA_STATES if state.casefold() not in found]
        if missing:
            raise RuntimeError(
                "All-India CM snapshot is incomplete; missing state evidence: "
                + ", ".join(missing[:28])
            )

    evidence = _source_pack(sources)
    prompt = f"""
Create a compact current-facts knowledge snapshot using ONLY the supplied evidence.

TOPIC:
{topic.question}

AS OF:
{as_of}

Rules:
- Do not use unstated model memory for current facts.
- Resolve conflicts in favor of newer official/primary evidence.
- Include concrete names, offices, versions, dates or status when the topic asks for them.
- If evidence is insufficient or contradictory, say so rather than inventing.
- Do not mention that this is a background task.
- Return the factual snapshot only, no JSON and no markdown citations.
""".strip()

    answer, answer_provider = await legacy.route_chat(
        "auto",
        [{"role": "user", "content": prompt}],
        settings,
        evidence,
        require_current=False,
        as_of=as_of,
    )
    answer = str(answer or "").strip()
    if len(answer) < 20:
        raise RuntimeError(f"Provider returned an unusable snapshot for {topic.id}.")

    await _upsert_verified(
        question=topic.question,
        answer=answer[:12000],
        aliases=list(dict.fromkeys((topic.question, *topic.aliases)))[:10],
        evidence_urls=_unique_urls(sources),
        dynamic=True,
        confidence=0.86,
        settings=settings,
    )

    elapsed_ms = round((time.perf_counter() - started) * 1000)
    row = {
        "id": topic.id,
        "ok": True,
        "source_count": len(sources),
        "search_provider": provider,
        "answer_provider": answer_provider,
        "refreshed_at": _now_iso(),
        "latency_ms": elapsed_ms,
    }
    _state["topics"][topic.id] = row
    _state["refresh_successes"] = int(_state["refresh_successes"]) + 1
    _state["last_success_at"] = row["refreshed_at"]
    return row


def _next_topics(settings: Any) -> list[LiveTopic]:
    global _cursor

    limit = max(1, min(4, int(getattr(settings, "v49_topics_per_cycle", 2))))
    selected: list[LiveTopic] = []

    if _pending and len(selected) < limit:
        query = _pending.popleft()
        _pending_seen.discard(query.casefold())
        selected.append(_topic_from_query(query))

    if bool(getattr(settings, "v49_default_topics_enabled", True)):
        while len(selected) < limit and DEFAULT_TOPICS:
            selected.append(DEFAULT_TOPICS[_cursor % len(DEFAULT_TOPICS)])
            _cursor = (_cursor + 1) % len(DEFAULT_TOPICS)

    return selected


async def refresh_cycle(settings: Any) -> dict[str, Any]:
    if not bool(getattr(settings, "v49_live_knowledge_enabled", True)):
        return {"ok": False, "skipped": "disabled"}
    if not _search_ready(settings):
        _state["last_error"] = "No live-search backend is configured."
        return {"ok": False, "skipped": "search-not-configured"}
    if not _storage_ready(settings):
        _state["last_error"] = "Persistent global knowledge storage is not configured."
        return {"ok": False, "skipped": "storage-not-configured"}

    _state["running"] = True
    _state["last_cycle_started_at"] = _now_iso()
    _state["cycles"] = int(_state["cycles"]) + 1
    results: list[dict[str, Any]] = []

    timeout = max(20.0, min(180.0, float(getattr(settings, "v49_topic_timeout_seconds", 120.0))))
    try:
        for topic in _next_topics(settings):
            try:
                row = await asyncio.wait_for(refresh_topic(settings, topic), timeout=timeout)
                results.append(row)
            except Exception as exc:
                message = str(exc)[:1200]
                _state["refresh_failures"] = int(_state["refresh_failures"]) + 1
                _state["last_error"] = message
                _state["topics"][topic.id] = {
                    "id": topic.id,
                    "ok": False,
                    "error": message,
                    "refreshed_at": _now_iso(),
                }
                results.append(_state["topics"][topic.id])
    finally:
        _state["running"] = False
        _state["last_cycle_finished_at"] = _now_iso()

    return {"ok": any(bool(item.get("ok")) for item in results), "results": results}


async def refresh_now(
    settings: Any,
    *,
    topic_id: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    if query:
        if not _safe_public_query(query):
            raise ValueError("Only public, non-sensitive current-information queries can be refreshed.")
        topic = _topic_from_query(query)
        result = await refresh_topic(settings, topic)
        return {"ok": True, "results": [result]}

    if topic_id:
        topic = next((item for item in DEFAULT_TOPICS if item.id == topic_id), None)
        if topic is None:
            raise ValueError("Unknown V49 live-knowledge topic.")
        result = await refresh_topic(settings, topic)
        return {"ok": True, "results": [result]}

    return await refresh_cycle(settings)


async def background_loop(settings: Any) -> None:
    delay = max(5, min(300, int(getattr(settings, "v49_startup_delay_seconds", 20))))
    await asyncio.sleep(delay)
    while True:
        try:
            await refresh_cycle(settings)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _state["last_error"] = str(exc)[:1200]
        interval = max(900, int(getattr(settings, "v49_refresh_interval_seconds", 7200)))
        await asyncio.sleep(interval)


def live_knowledge_status(settings: Any) -> dict[str, Any]:
    interval = max(900, int(getattr(settings, "v49_refresh_interval_seconds", 7200)))
    return {
        "ok": True,
        "version": "v49",
        "name": "Vasuki Continuous Live Knowledge Brain",
        "enabled": bool(getattr(settings, "v49_live_knowledge_enabled", True)),
        "search_ready": _search_ready(settings),
        "storage_ready": _storage_ready(settings),
        "refresh_interval_seconds": interval,
        "topics_per_cycle": max(1, min(4, int(getattr(settings, "v49_topics_per_cycle", 2)))),
        "default_topics": [
            {"id": item.id, "question": item.question}
            for item in DEFAULT_TOPICS
        ],
        "pending_adaptive_queries": len(_pending),
        "runtime": {
            "running": bool(_state["running"]),
            "last_cycle_started_at": _state["last_cycle_started_at"],
            "last_cycle_finished_at": _state["last_cycle_finished_at"],
            "last_success_at": _state["last_success_at"],
            "cycles": int(_state["cycles"]),
            "refresh_successes": int(_state["refresh_successes"]),
            "refresh_failures": int(_state["refresh_failures"]),
            "last_error": str(_state["last_error"]),
            "topics": dict(_state["topics"]),
        },
        "persistence": "existing Supabase verified global knowledge",
        "query_learning": "public freshness-sensitive queries are queued for background refresh",
        "privacy": "email/phone/password/token-like queries are not promoted to shared knowledge",
        "new_database_migration_required": False,
        "new_api_key_required": False,
        "important_limit": (
            "No system can pre-store all changing information on the internet. "
            "V49 continuously refreshes curated high-value topics plus public current queries users actually ask."
        ),
        "hosting_note": (
            "Background refresh runs while the backend process is awake. "
            "A free host that sleeps cannot collect continuously while suspended."
        ),
    }
