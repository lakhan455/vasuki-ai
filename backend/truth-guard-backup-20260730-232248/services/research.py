from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

import httpx

from app.config import Settings


# These terms usually mean that model memory is not safe enough and live search
# should be forced even when the frontend web toggle is off.
FRESHNESS_TERMS = (
    "current", "currently", "latest", "today", "now", "recent", "live", "this year",
    "abhi", "abi", "filhal", "haal mein", "aaj", "naya", "new update",
    "present", "updated", "newest", "as of", "breaking", "score", "schedule", "price",
    "weather", "release date", "version", "ceo", "president", "prime minister",
    "chief minister", "minister", "governor", "office holder", "law", "rule", "regulation",
    "अभी", "वर्तमान", "वर्तमान में", "आज", "नवीनतम", "लेटेस्ट", "ताजा", "ताज़ा",
    "मुख्यमंत्री", "प्रधानमंत्री", "राष्ट्रपति", "मंत्री", "राज्यपाल", "सीएम", "कीमत",
    "मौसम", "स्कोर", "शेड्यूल", "रिलीज", "नियम", "कानून",
)

INDIA_TERMS = (
    "india", "indian", "ind", "bharat", "भारत", "इंडिया", "rajasthan", "राजस्थान", "state", "states",
    "राज्य", "union territory", "केंद्र शासित", "chief minister", "मुख्यमंत्री", " cm ",
)

OFFICEHOLDER_TERMS = (
    "chief minister", "मुख्यमंत्री", " cm ", "president", "राष्ट्रपति", "prime minister",
    "प्रधानमंत्री", "governor", "राज्यपाल", "minister", "मंत्री", "ceo", "chairman",
    "mayor", "office holder", "mukhyamantri", "pradhanmantri", "rashtrapati",
    "rajyapal", "mantri",
)

LIST_TERMS = (
    "all state", "all states", "list", "every state", "सभी राज्य", "सारे राज्य",
    "पूरी सूची", "लिस्ट", "नाम की सूची", "sabhi rajya", "sabhi rajyon", "sare rajya",
    "all cm", "all chief minister",
)


def needs_live_web(query: str) -> bool:
    """Return True when answering from static model memory could be stale."""
    normalized = f" {query.casefold()} "
    return any(term in normalized for term in FRESHNESS_TERMS) or _is_officeholder_query(query)


def _is_india_query(query: str) -> bool:
    normalized = f" {query.casefold()} "
    return any(term in normalized for term in INDIA_TERMS)


def _is_officeholder_query(query: str) -> bool:
    normalized = f" {query.casefold()} "
    return any(term in normalized for term in OFFICEHOLDER_TERMS)


def _is_list_query(query: str) -> bool:
    normalized = f" {query.casefold()} "
    return any(term in normalized for term in LIST_TERMS)


def _trusted_source_rank(url: str) -> int:
    """Lower values are preferred. Official public-sector domains come first."""
    host = urlparse(url).netloc.casefold().split(":", 1)[0]
    if host.endswith(".gov.in") or host.endswith(".nic.in") or host == "india.gov.in":
        return 0
    if host.endswith(".gov") or host.endswith(".go.uk") or host.endswith(".europa.eu"):
        return 1
    if host.endswith(".edu") or host.endswith(".ac.in"):
        return 2
    return 3


def _clean_result(item: dict) -> dict:
    content = (item.get("raw_content") or item.get("content") or "").strip()
    # Keep enough text for lists/tables while protecting the LLM context window.
    content = content[:7000]
    return {
        "title": item.get("title", "Source"),
        "url": item.get("url", ""),
        "content": content,
        "score": item.get("score"),
        "published_date": item.get("published_date"),
    }


def _build_search_queries(query: str, as_of: str, require_current: bool) -> list[str]:
    prefix = (
        f"As of {as_of}, find the current verified answer to: {query}. "
        "Prioritize official primary sources and pages that clearly show the current office holder or latest status. "
        "Ignore archived, historical, cached, or undated lists when a newer source conflicts."
        if require_current
        else query
    )
    queries = [prefix]

    # A single broad result is often incomplete for all-state office-holder lists.
    # These extra searches improve recall and make the model less likely to reuse old memory.
    if _is_india_query(query) and _is_officeholder_query(query) and _is_list_query(query):
        queries.extend(
            [
                f"As of {as_of}, current Chief Ministers of all Indian states complete updated list",
                f"As of {as_of}, current Chief Ministers and heads of government of Indian Union Territories updated list",
                f"As of {as_of}, official state government pages current chief ministers India",
            ]
        )

    # Preserve order while removing duplicates.
    return list(dict.fromkeys(queries))


async def tavily_search(
    query: str,
    settings: Settings,
    max_results: int = 8,
    *,
    official_only: bool = False,
) -> list[dict]:
    if not settings.tavily_api_key:
        return []

    payload: dict = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "search_depth": "advanced",
        "chunks_per_source": 3,
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": "text",
        "topic": "general",
    }
    if _is_india_query(query):
        payload["country"] = "india"
    if official_only and _is_india_query(query):
        payload["include_domains"] = ["gov.in", "nic.in", "india.gov.in"]

    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        response = await client.post("https://api.tavily.com/search", json=payload)
        response.raise_for_status()
        data = response.json()

    return [_clean_result(item) for item in data.get("results", []) if item.get("url")]


async def exa_search(query: str, settings: Settings, max_results: int = 8) -> list[dict]:
    if not settings.exa_api:
        return []

    headers = {"x-api-key": settings.exa_api, "Content-Type": "application/json"}
    payload: dict = {
        "query": query,
        "numResults": max_results,
        "useAutoprompt": True,
        "contents": {"text": {"maxCharacters": 5000}},
    }
    if _is_india_query(query) and _is_officeholder_query(query):
        payload["includeDomains"] = ["gov.in", "nic.in", "india.gov.in"]

    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        response = await client.post("https://api.exa.ai/search", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    return [
        {
            "title": item.get("title", "Source"),
            "url": item.get("url", ""),
            "content": (item.get("text") or "")[:5000],
            "score": item.get("score"),
            "published_date": item.get("publishedDate"),
        }
        for item in data.get("results", [])
        if item.get("url")
    ]


def _dedupe_and_rank(results: list[dict], max_results: int) -> list[dict]:
    unique: dict[str, dict] = {}
    for item in results:
        url = item.get("url", "").strip()
        if not url:
            continue
        existing = unique.get(url)
        if existing is None or len(item.get("content", "")) > len(existing.get("content", "")):
            unique[url] = item

    ranked = sorted(
        unique.values(),
        key=lambda item: (
            _trusted_source_rank(item.get("url", "")),
            -(float(item.get("score")) if item.get("score") is not None else 0.0),
        ),
    )
    return ranked[:max_results]


async def search_web(
    query: str,
    settings: Settings,
    max_results: int = 8,
    *,
    require_current: bool = False,
    as_of: str | None = None,
) -> tuple[list[dict], str]:
    """Search with official-source preference and return a merged, ranked result set."""
    as_of = as_of or date.today().isoformat()
    queries = _build_search_queries(query, as_of, require_current)
    collected: list[dict] = []
    providers_used: list[str] = []
    errors: list[str] = []

    for search_query in queries:
        # For Indian office-holder questions, try official government domains first.
        if _is_india_query(search_query) and _is_officeholder_query(search_query):
            try:
                official = await tavily_search(
                    search_query,
                    settings,
                    max_results=min(6, max_results),
                    official_only=True,
                )
                if official:
                    collected.extend(official)
                    if "tavily" not in providers_used:
                        providers_used.append("tavily")
            except Exception as exc:
                errors.append(f"tavily-official: {exc}")

        try:
            general = await tavily_search(
                search_query,
                settings,
                max_results=min(8, max_results),
                official_only=False,
            )
            if general:
                collected.extend(general)
                if "tavily" not in providers_used:
                    providers_used.append("tavily")
        except Exception as exc:
            errors.append(f"tavily: {exc}")

        # Stop early after enough diverse sources to reduce API usage.
        if len(_dedupe_and_rank(collected, max_results)) >= max_results:
            break

    if len(_dedupe_and_rank(collected, max_results)) < max_results:
        try:
            exa = await exa_search(queries[0], settings, max_results=max_results)
            if exa:
                collected.extend(exa)
                providers_used.append("exa")
        except Exception as exc:
            errors.append(f"exa: {exc}")

    results = _dedupe_and_rank(collected, max_results)
    if results:
        return results, "+".join(dict.fromkeys(providers_used)) or "web"
    return [], "; ".join(errors) if errors else "No research API configured"
