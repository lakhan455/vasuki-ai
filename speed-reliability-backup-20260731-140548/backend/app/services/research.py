from __future__ import annotations

import asyncio
import re
import time
from datetime import date, datetime, timezone
from urllib.parse import urlparse

import httpx

from app.config import Settings


# Any answer in these categories can change without the model being updated.
FRESHNESS_TERMS = (
    "current", "currently", "latest", "today", "now", "recent", "live", "this year",
    "2026", "abhi", "abi", "filhal", "haal mein", "aaj", "naya", "new update",
    "present", "updated", "newest", "as of", "breaking", "score", "schedule", "price",
    "weather", "release date", "version", "ceo", "president", "prime minister",
    "chief minister", "minister", "governor", "office holder", "law", "rule", "regulation",
    "election", "result", "winner", "cabinet", "appointment", "resigned", "sworn in",
    "अभी", "वर्तमान", "वर्तमान में", "आज", "नवीनतम", "लेटेस्ट", "ताजा", "ताज़ा",
    "मुख्यमंत्री", "प्रधानमंत्री", "राष्ट्रपति", "मंत्री", "राज्यपाल", "सीएम", "कीमत",
    "मौसम", "स्कोर", "शेड्यूल", "रिलीज", "नियम", "कानून", "चुनाव", "नतीजे",
)

DYNAMIC_FACT_TERMS = (
    "stock", "share price", "crypto", "exchange rate", "market", "news", "sports",
    "flight", "train", "availability", "deadline", "admission", "vacancy", "job opening",
    "software version", "api", "documentation", "policy", "tax", "interest rate",
    "medical guideline", "treatment guideline", "recall", "outage", "status",
)

OFFICEHOLDER_TERMS = (
    "chief minister", "मुख्यमंत्री", " cm ", "president", "राष्ट्रपति", "prime minister",
    "प्रधानमंत्री", "governor", "राज्यपाल", "minister", "मंत्री", "ceo", "chairman",
    "mayor", "office holder", "mukhyamantri", "pradhanmantri", "rashtrapati",
    "rajyapal", "mantri", "सी एम", "cm of", "who is the cm", "kon cm", "ka cm",
)

INDIA_TERMS = (
    "india", "indian", " ind ", "bharat", "भारत", "इंडिया", "rajasthan", "राजस्थान",
    "tamil nadu", "तमिलनाडु", "state", "states", "राज्य", "union territory",
    "केंद्र शासित", "chief minister", "मुख्यमंत्री", " cm ",
)

ALL_STATE_CM_TERMS = (
    "all state cm", "all states cm", "all state chief minister", "all states chief minister",
    "chief ministers of all states", "all indian states cm", "all india state cm",
    "सभी राज्यों के मुख्यमंत्री", "सारे राज्यों के मुख्यमंत्री", "सभी राज्य के मुख्यमंत्री",
    "राज्यों के सीएम", "sabhi rajya ke cm", "sabhi rajyon ke cm", "sare state ke cm",
    "all state ke cm", "all states ke cm", "state ke cm ki list", "all cm list",
)

# User's spelling/roman-Hindi variants are intentionally covered.
ALL_STATE_CM_REGEX = re.compile(
    r"(?:all|sabhi|sare|saare|सभी|सारे).{0,30}(?:state|states|rajya|rajyon|राज्य).{0,30}"
    r"(?:cm|chief\s*minister|mukhyamantri|मुख्यमंत्री|सीएम)",
    re.IGNORECASE | re.DOTALL,
)

FACTUAL_PREFIXES = (
    "who ", "what ", "when ", "where ", "which ", "how many ", "how much ",
    "tell me", "give me", "list ", "name ", "is ", "are ",
    "कौन", "क्या", "कब", "कहाँ", "कितने", "बताओ", "सूची", "नाम",
    "kon", "kya", "kab", "kaha", "kitne", "batao", "list do", "name do",
)

NO_WEB_INTENT_TERMS = (
    "write a poem", "write a story", "rewrite", "translate", "summarize this", "grammar",
    "make a caption", "create a logo prompt", "generate an image", "image create",
    "write code", "fix this code", "debug this code", "html code", "css code",
)

INDIA_STATES = (
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa",
    "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
    "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal",
)

OFFICIAL_INDIA_DOMAINS = (
    "*.gov.in", "*.nic.in", "india.gov.in", "pmindia.gov.in", "pib.gov.in",
)

REPUTABLE_NEWS_HOSTS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "thehindu.com",
    "indianexpress.com", "hindustantimes.com", "ndtv.com", "economictimes.indiatimes.com",
    "timesofindia.indiatimes.com", "deccanherald.com", "business-standard.com",
}

# In-memory cache avoids spending 28 search requests every time the same all-state list is asked.
_STATE_CACHE: dict[str, tuple[float, list[dict]]] = {}
_STATE_CACHE_TTL_SECONDS = 12 * 60 * 60


def _normalized(query: str) -> str:
    return f" {re.sub(r'\s+', ' ', query.casefold()).strip()} "


def is_all_india_state_cm_query(query: str) -> bool:
    normalized = _normalized(query)
    return any(term in normalized for term in ALL_STATE_CM_TERMS) or bool(ALL_STATE_CM_REGEX.search(query))


def _is_officeholder_query(query: str) -> bool:
    normalized = _normalized(query)
    return any(term in normalized for term in OFFICEHOLDER_TERMS)


def _is_india_query(query: str) -> bool:
    normalized = _normalized(query)
    return any(term in normalized for term in INDIA_TERMS)


def _looks_factual(query: str) -> bool:
    normalized = _normalized(query)
    if any(term in normalized for term in NO_WEB_INTENT_TERMS):
        return False
    if any(term in normalized for term in DYNAMIC_FACT_TERMS):
        return True
    stripped = normalized.strip()
    if any(stripped.startswith(prefix) for prefix in FACTUAL_PREFIXES):
        return True
    # Many Roman-Hindi factual requests do not use a question mark.
    return any(token in normalized for token in (" kaun ", " kon ", " kya ", " bata ", " list "))


def needs_live_web(query: str) -> bool:
    """Fail closed for time-sensitive and factual questions instead of trusting stale model memory."""
    normalized = _normalized(query)
    return (
        any(term in normalized for term in FRESHNESS_TERMS)
        or _is_officeholder_query(query)
        or is_all_india_state_cm_query(query)
        or _looks_factual(query)
    )


def _host(url: str) -> str:
    return urlparse(url).netloc.casefold().split(":", 1)[0].removeprefix("www.")


def _source_kind(url: str) -> str:
    host = _host(url)
    if host.endswith(".gov.in") or host.endswith(".nic.in") or host in {
        "india.gov.in", "pmindia.gov.in", "pib.gov.in"
    }:
        return "official"
    if any(host == item or host.endswith("." + item) for item in REPUTABLE_NEWS_HOSTS):
        return "reputable_news"
    if host.endswith(".gov") or host.endswith(".go.uk") or host.endswith(".europa.eu"):
        return "official"
    if host.endswith(".edu") or host.endswith(".ac.in"):
        return "academic"
    return "other"


def _parse_date(value: str | None) -> float:
    if not value:
        return 0.0
    candidate = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(candidate).timestamp()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return 0.0


def _trust_rank(item: dict) -> tuple[int, float, float]:
    kind = item.get("source_type") or _source_kind(item.get("url", ""))
    kind_rank = {"official": 0, "reputable_news": 1, "academic": 2, "other": 3}.get(kind, 3)
    published = _parse_date(item.get("published_date"))
    score = float(item.get("score") or 0.0)
    # Lower tuple is better; recent dates and higher relevance are preferred inside a trust tier.
    return kind_rank, -published, -score


def _clean_result(item: dict, *, entity: str | None = None, content_limit: int = 2400) -> dict:
    content = (item.get("raw_content") or item.get("content") or item.get("text") or "").strip()
    content = re.sub(r"\n{3,}", "\n\n", content)[:content_limit]
    url = (item.get("url") or "").strip()
    return {
        "title": item.get("title") or "Source",
        "url": url,
        "content": content,
        "score": item.get("score"),
        "published_date": item.get("published_date") or item.get("publishedDate"),
        "source_type": _source_kind(url),
        "entity": entity,
    }


def _dedupe_and_rank(results: list[dict], max_results: int) -> list[dict]:
    unique: dict[str, dict] = {}
    for item in results:
        url = (item.get("url") or "").strip()
        if not url or not item.get("content"):
            continue
        existing = unique.get(url)
        if existing is None or len(item.get("content", "")) > len(existing.get("content", "")):
            unique[url] = item
    return sorted(unique.values(), key=_trust_rank)[:max_results]


async def tavily_search(
    query: str,
    settings: Settings,
    max_results: int = 8,
    *,
    topic: str = "general",
    time_range: str | None = None,
    include_domains: list[str] | tuple[str, ...] | None = None,
    search_depth: str = "advanced",
    entity: str | None = None,
    content_limit: int = 2400,
) -> list[dict]:
    if not settings.tavily_api_key:
        return []

    payload: dict = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "search_depth": search_depth,
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": "text",
        "topic": topic,
    }
    if search_depth == "advanced":
        payload["chunks_per_source"] = 3
    if topic == "general" and _is_india_query(query):
        payload["country"] = "india"
    if time_range:
        payload["time_range"] = time_range
    if include_domains:
        payload["include_domains"] = list(include_domains)

    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        response = await client.post("https://api.tavily.com/search", json=payload)
        response.raise_for_status()
        data = response.json()

    return [
        _clean_result(item, entity=entity, content_limit=content_limit)
        for item in data.get("results", [])
        if item.get("url")
    ]


async def exa_search(
    query: str,
    settings: Settings,
    max_results: int = 8,
    *,
    entity: str | None = None,
    content_limit: int = 2400,
) -> list[dict]:
    if not settings.exa_api:
        return []

    headers = {"x-api-key": settings.exa_api, "Content-Type": "application/json"}
    payload: dict = {
        "query": query,
        "numResults": max_results,
        "useAutoprompt": True,
        "contents": {"text": {"maxCharacters": content_limit}},
    }
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        response = await client.post("https://api.exa.ai/search", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    return [
        _clean_result(item, entity=entity, content_limit=content_limit)
        for item in data.get("results", [])
        if item.get("url")
    ]


def _select_state_evidence(results: list[dict]) -> list[dict]:
    ranked = _dedupe_and_rank(results, 8)
    if not ranked:
        return []

    selected: list[dict] = []
    official = next((item for item in ranked if item.get("source_type") == "official"), None)
    recent = next(
        (
            item for item in sorted(ranked, key=lambda x: -_parse_date(x.get("published_date")))
            if item.get("source_type") in {"official", "reputable_news"}
        ),
        None,
    )
    for item in (official, recent, ranked[0]):
        if item and all(existing.get("url") != item.get("url") for existing in selected):
            # Two short pieces of evidence per state keep the verifier context manageable.
            item = dict(item)
            item["content"] = item.get("content", "")[:1200]
            selected.append(item)
        if len(selected) >= 2:
            break
    return selected


async def _search_one_state_cm(state: str, settings: Settings, as_of: str, semaphore: asyncio.Semaphore) -> list[dict]:
    cache_key = f"{as_of}:{state.casefold()}"
    cached = _STATE_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < _STATE_CACHE_TTL_SECONDS:
        return cached[1]

    query = (
        f"As of {as_of}, who is the current Chief Minister of {state}, India? "
        "Find the newest official government, oath/appointment, or highly reputable current source. "
        "Exclude former chief ministers and pages describing a previous administration."
    )
    async with semaphore:
        results: list[dict] = []
        try:
            results.extend(
                await tavily_search(
                    query,
                    settings,
                    max_results=5,
                    topic="general",
                    search_depth="basic",
                    entity=state,
                    content_limit=1600,
                )
            )
        except Exception:
            pass
        if not results:
            try:
                results.extend(
                    await exa_search(query, settings, max_results=5, entity=state, content_limit=1600)
                )
            except Exception:
                pass

    evidence = _select_state_evidence(results)
    _STATE_CACHE[cache_key] = (time.monotonic(), evidence)
    return evidence


async def search_all_india_state_cms(settings: Settings, as_of: str) -> tuple[list[dict], str]:
    """Resolve each state separately so one stale national list cannot poison the answer."""
    semaphore = asyncio.Semaphore(6)
    batches = await asyncio.gather(
        *(_search_one_state_cm(state, settings, as_of, semaphore) for state in INDIA_STATES)
    )
    results = [item for batch in batches for item in batch]
    provider = "tavily/exa per-state verification" if results else "No research API configured or no evidence returned"
    return results, provider


async def search_web(
    query: str,
    settings: Settings,
    max_results: int = 10,
    *,
    require_current: bool = False,
    as_of: str | None = None,
) -> tuple[list[dict], str]:
    """Search current evidence with official-source preference and a recent-source cross-check."""
    as_of = as_of or date.today().isoformat()

    if is_all_india_state_cm_query(query):
        return await search_all_india_state_cms(settings, as_of)

    base_query = (
        f"As of {as_of}, verify the newest currently valid answer to this question: {query}. "
        "Use primary sources where possible. Treat resignations, appointments, election results, oath ceremonies, "
        "official corrections, and newer dated reports as overriding older pages."
        if require_current
        else query
    )

    jobs: list = [
        tavily_search(
            base_query,
            settings,
            max_results=min(max_results, 8),
            topic="general",
            search_depth="advanced",
            content_limit=3000,
        )
    ]

    # Current queries get an independent recent-news pass. This is crucial when an old official bio remains indexed.
    if require_current:
        jobs.append(
            tavily_search(
                base_query,
                settings,
                max_results=min(max_results, 8),
                topic="news",
                time_range="year",
                search_depth="advanced",
                content_limit=2500,
            )
        )

    # Indian office holders get a primary-source-only pass in addition to the open web.
    if _is_india_query(query) and _is_officeholder_query(query):
        jobs.append(
            tavily_search(
                base_query,
                settings,
                max_results=min(max_results, 8),
                topic="general",
                include_domains=OFFICIAL_INDIA_DOMAINS,
                search_depth="advanced",
                content_limit=3000,
            )
        )

    collected: list[dict] = []
    errors: list[str] = []
    completed = await asyncio.gather(*jobs, return_exceptions=True)
    for result in completed:
        if isinstance(result, Exception):
            errors.append(str(result))
        else:
            collected.extend(result)

    ranked = _dedupe_and_rank(collected, max_results)
    if len(ranked) < min(4, max_results):
        try:
            ranked = _dedupe_and_rank(
                ranked + await exa_search(base_query, settings, max_results=max_results, content_limit=2800),
                max_results,
            )
        except Exception as exc:
            errors.append(f"exa: {exc}")

    if ranked:
        return ranked, "tavily+exa" if settings.exa_api else "tavily"
    return [], "; ".join(errors) if errors else "No research API configured"
