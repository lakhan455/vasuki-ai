from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
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
    "à¤…à¤­à¥€", "à¤µà¤°à¥à¤¤à¤®à¤¾à¤¨", "à¤µà¤°à¥à¤¤à¤®à¤¾à¤¨ à¤®à¥‡à¤‚", "à¤†à¤œ", "à¤¨à¤µà¥€à¤¨à¤¤à¤®", "à¤²à¥‡à¤Ÿà¥‡à¤¸à¥à¤Ÿ", "à¤¤à¤¾à¤œà¤¾", "à¤¤à¤¾à¤œà¤¼à¤¾",
    "à¤®à¥à¤–à¥à¤¯à¤®à¤‚à¤¤à¥à¤°à¥€", "à¤ªà¥à¤°à¤§à¤¾à¤¨à¤®à¤‚à¤¤à¥à¤°à¥€", "à¤°à¤¾à¤·à¥à¤Ÿà¥à¤°à¤ªà¤¤à¤¿", "à¤®à¤‚à¤¤à¥à¤°à¥€", "à¤°à¤¾à¤œà¥à¤¯à¤ªà¤¾à¤²", "à¤¸à¥€à¤à¤®", "à¤•à¥€à¤®à¤¤",
    "à¤®à¥Œà¤¸à¤®", "à¤¸à¥à¤•à¥‹à¤°", "à¤¶à¥‡à¤¡à¥à¤¯à¥‚à¤²", "à¤°à¤¿à¤²à¥€à¤œ", "à¤¨à¤¿à¤¯à¤®", "à¤•à¤¾à¤¨à¥‚à¤¨", "à¤šà¥à¤¨à¤¾à¤µ", "à¤¨à¤¤à¥€à¤œà¥‡",
)

DYNAMIC_FACT_TERMS = (
    "stock", "share price", "crypto", "exchange rate", "market", "news", "sports",
    "flight", "train", "availability", "deadline", "admission", "vacancy", "job opening",
    "software version", "api", "documentation", "policy", "tax", "interest rate",
    "medical guideline", "treatment guideline", "recall", "outage", "status",
    "subscriber", "subscribers", "followers", "most subscribed", "highest subscribed",
    "box office", "ott", "streaming availability", "rating", "ranking",
)

OFFICEHOLDER_TERMS = (
    "chief minister", "à¤®à¥à¤–à¥à¤¯à¤®à¤‚à¤¤à¥à¤°à¥€", " cm ", "president", "à¤°à¤¾à¤·à¥à¤Ÿà¥à¤°à¤ªà¤¤à¤¿", "prime minister",
    "à¤ªà¥à¤°à¤§à¤¾à¤¨à¤®à¤‚à¤¤à¥à¤°à¥€", "governor", "à¤°à¤¾à¤œà¥à¤¯à¤ªà¤¾à¤²", "minister", "à¤®à¤‚à¤¤à¥à¤°à¥€", "ceo", "chairman",
    "mayor", "office holder", "mukhyamantri", "pradhanmantri", "rashtrapati",
    "rajyapal", "mantri", "à¤¸à¥€ à¤à¤®", "cm of", "who is the cm", "kon cm", "ka cm",
)

INDIA_TERMS = (
    "india", "indian", " ind ", "bharat", "à¤­à¤¾à¤°à¤¤", "à¤‡à¤‚à¤¡à¤¿à¤¯à¤¾", "rajasthan", "à¤°à¤¾à¤œà¤¸à¥à¤¥à¤¾à¤¨",
    "tamil nadu", "à¤¤à¤®à¤¿à¤²à¤¨à¤¾à¤¡à¥", "state", "states", "à¤°à¤¾à¤œà¥à¤¯", "union territory",
    "à¤•à¥‡à¤‚à¤¦à¥à¤° à¤¶à¤¾à¤¸à¤¿à¤¤", "chief minister", "à¤®à¥à¤–à¥à¤¯à¤®à¤‚à¤¤à¥à¤°à¥€", " cm ",
)

ALL_STATE_CM_TERMS = (
    "all state cm", "all states cm", "all state chief minister", "all states chief minister",
    "chief ministers of all states", "all indian states cm", "all india state cm",
    "à¤¸à¤­à¥€ à¤°à¤¾à¤œà¥à¤¯à¥‹à¤‚ à¤•à¥‡ à¤®à¥à¤–à¥à¤¯à¤®à¤‚à¤¤à¥à¤°à¥€", "à¤¸à¤¾à¤°à¥‡ à¤°à¤¾à¤œà¥à¤¯à¥‹à¤‚ à¤•à¥‡ à¤®à¥à¤–à¥à¤¯à¤®à¤‚à¤¤à¥à¤°à¥€", "à¤¸à¤­à¥€ à¤°à¤¾à¤œà¥à¤¯ à¤•à¥‡ à¤®à¥à¤–à¥à¤¯à¤®à¤‚à¤¤à¥à¤°à¥€",
    "à¤°à¤¾à¤œà¥à¤¯à¥‹à¤‚ à¤•à¥‡ à¤¸à¥€à¤à¤®", "sabhi rajya ke cm", "sabhi rajyon ke cm", "sare state ke cm",
    "all state ke cm", "all states ke cm", "state ke cm ki list", "all cm list",
)

# User's spelling/roman-Hindi variants are intentionally covered.
ALL_STATE_CM_REGEX = re.compile(
    r"(?:all|sabhi|sare|saare|à¤¸à¤­à¥€|à¤¸à¤¾à¤°à¥‡).{0,30}(?:state|states|rajya|rajyon|à¤°à¤¾à¤œà¥à¤¯).{0,30}"
    r"(?:cm|chief\s*minister|mukhyamantri|à¤®à¥à¤–à¥à¤¯à¤®à¤‚à¤¤à¥à¤°à¥€|à¤¸à¥€à¤à¤®)",
    re.IGNORECASE | re.DOTALL,
)

FACTUAL_PREFIXES = (
    "who ", "what ", "when ", "where ", "which ", "how many ", "how much ",
    "tell me", "give me", "list ", "name ", "is ", "are ",
    "à¤•à¥Œà¤¨", "à¤•à¥à¤¯à¤¾", "à¤•à¤¬", "à¤•à¤¹à¤¾à¤", "à¤•à¤¿à¤¤à¤¨à¥‡", "à¤¬à¤¤à¤¾à¤“", "à¤¸à¥‚à¤šà¥€", "à¤¨à¤¾à¤®",
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


@dataclass(frozen=True, slots=True)
class ResearchProfile:
    key: str
    label: str
    keywords: tuple[str, ...]
    primary_domains: tuple[str, ...]
    reference_domains: tuple[str, ...]


RESEARCH_PROFILES = (
    ResearchProfile(
        key="movies",
        label="movies, TV and streaming",
        keywords=(
            "movie", "film", "cinema", "actor", "actress", "cast", "director",
            "trailer", "box office", "web series", "tv series", "episode", "season",
            "ott", "streaming", "netflix", "prime video", "disney+", "hotstar",
            "imdb", "rotten tomatoes", "metacritic", "मूवी", "फिल्म", "वेब सीरीज",
        ),
        primary_domains=(
            "netflix.com", "primevideo.com", "disneyplus.com", "hotstar.com",
            "max.com", "hbo.com", "apple.com", "peacocktv.com", "paramountplus.com",
            "sonypictures.com", "warnerbros.com", "universalpictures.com",
            "paramount.com", "marvel.com", "starwars.com",
        ),
        reference_domains=(
            "imdb.com", "rottentomatoes.com", "metacritic.com", "boxofficemojo.com",
            "justwatch.com", "variety.com", "hollywoodreporter.com", "deadline.com",
        ),
    ),
    ResearchProfile(
        key="youtube_social",
        label="YouTube and social platforms",
        keywords=(
            "youtube", "youtuber", "subscriber", "subscribers", "channel",
            "instagram", "facebook", "twitter", "x.com", "tiktok", "followers",
            "सोशल मीडिया", "सब्सक्राइबर", "यूट्यूब",
        ),
        primary_domains=(
            "youtube.com", "blog.youtube", "about.youtube", "support.google.com",
            "instagram.com", "facebook.com", "x.com", "tiktok.com",
        ),
        reference_domains=(
            "socialblade.com", "tubefilter.com", "statista.com", "variety.com",
            "reuters.com", "forbes.com",
        ),
    ),
    ResearchProfile(
        key="games",
        label="video games",
        keywords=(
            "game", "gaming", "gta", "playstation", "xbox", "nintendo", "steam",
            "epic games", "release date", "system requirements", "गेम",
        ),
        primary_domains=(
            "rockstargames.com", "playstation.com", "xbox.com", "nintendo.com",
            "steampowered.com", "store.epicgames.com", "ea.com", "ubisoft.com",
            "activision.com", "bethesda.net",
        ),
        reference_domains=(
            "ign.com", "gamespot.com", "polygon.com", "eurogamer.net",
            "pcgamer.com", "theverge.com",
        ),
    ),
    ResearchProfile(
        key="technology",
        label="technology, software and APIs",
        keywords=(
            "software", "api", "sdk", "framework", "library", "version", "documentation",
            "android", "ios", "windows", "linux", "openai", "google ai", "github",
            "python", "javascript", "typescript", "next.js", "flutter", "टेक",
        ),
        primary_domains=(
            "github.com", "docs.github.com", "developer.android.com", "developer.apple.com",
            "learn.microsoft.com", "developers.google.com", "cloud.google.com",
            "platform.openai.com", "openai.com", "docs.python.org", "nodejs.org",
            "nextjs.org", "flutter.dev",
        ),
        reference_domains=(
            "stackoverflow.com", "developer.mozilla.org", "theverge.com",
            "arstechnica.com", "techcrunch.com",
        ),
    ),
    ResearchProfile(
        key="medical",
        label="health and medicine",
        keywords=(
            "health", "medical", "medicine", "disease", "symptom", "treatment",
            "drug", "vaccine", "doctor", "hospital", "स्वास्थ्य", "दवा", "बीमारी",
        ),
        primary_domains=(
            "who.int", "cdc.gov", "nih.gov", "fda.gov", "nhs.uk", "icmr.gov.in",
            "mohfw.gov.in", "clinicaltrials.gov",
        ),
        reference_domains=(
            "pubmed.ncbi.nlm.nih.gov", "cochranelibrary.com", "mayoclinic.org",
            "nejm.org", "thelancet.com", "bmj.com",
        ),
    ),
    ResearchProfile(
        key="finance",
        label="finance, markets and companies",
        keywords=(
            "stock", "share price", "market cap", "crypto", "finance", "bank",
            "interest rate", "company results", "earnings", "nse", "bse", "rbi",
            "शेयर", "स्टॉक", "बैंक",
        ),
        primary_domains=(
            "rbi.org.in", "sebi.gov.in", "nseindia.com", "bseindia.com", "sec.gov",
            "investor.gov",
        ),
        reference_domains=(
            "reuters.com", "bloomberg.com", "ft.com", "wsj.com", "cnbc.com",
            "moneycontrol.com", "economictimes.indiatimes.com",
        ),
    ),
    ResearchProfile(
        key="sports",
        label="sports",
        keywords=(
            "sports", "cricket", "football", "soccer", "nba", "nfl", "ipl", "match",
            "score", "schedule", "standings", "player", "खेल", "क्रिकेट", "मैच",
        ),
        primary_domains=(
            "icc-cricket.com", "bcci.tv", "iplt20.com", "fifa.com", "uefa.com",
            "nba.com", "nfl.com", "nhl.com", "mlb.com", "olympics.com",
        ),
        reference_domains=(
            "espn.com", "espncricinfo.com", "bbc.com", "skysports.com", "reuters.com",
        ),
    ),
    ResearchProfile(
        key="travel",
        label="travel and transport",
        keywords=(
            "travel", "trip", "flight", "train", "hotel", "visa", "tourism", "airport",
            "railway", "यात्रा", "फ्लाइट", "ट्रेन", "होटल",
        ),
        primary_domains=(
            "irctc.co.in", "indianrail.gov.in", "airindia.com", "goindigo.in",
            "emirates.com", "qatarairways.com", "iata.org", "incredibleindia.gov.in",
        ),
        reference_domains=(
            "tripadvisor.com", "lonelyplanet.com", "skyscanner.com", "booking.com",
            "reuters.com",
        ),
    ),
    ResearchProfile(
        key="research",
        label="academic research",
        keywords=(
            "research paper", "doi", "journal", "study", "academic", "thesis",
            "literature review", "paper", "रिसर्च", "शोध पत्र",
        ),
        primary_domains=(
            "doi.org", "pubmed.ncbi.nlm.nih.gov", "arxiv.org", "nature.com",
            "science.org", "springer.com", "sciencedirect.com", "ieee.org",
        ),
        reference_domains=(
            "semanticscholar.org", "crossref.org", "researchgate.net", "scholar.google.com",
        ),
    ),
)

PRIMARY_PLATFORM_DOMAINS = {
    domain for profile in RESEARCH_PROFILES for domain in profile.primary_domains
}
TRUSTED_REFERENCE_DOMAINS = {
    domain for profile in RESEARCH_PROFILES for domain in profile.reference_domains
}


def _domain_matches(host: str, domains: tuple[str, ...] | set[str]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def classify_research_profile(query: str) -> ResearchProfile | None:
    normalized = _normalized(query)
    best: ResearchProfile | None = None
    best_score = 0
    for profile in RESEARCH_PROFILES:
        score = sum(1 for keyword in profile.keywords if keyword in normalized)
        if score > best_score:
            best = profile
            best_score = score
    return best


def should_auto_research(query: str) -> bool:
    """Automatically research factual platform/domain questions even without the web toggle."""
    return bool(classify_research_profile(query) and _looks_factual(query))


# In-memory cache avoids spending 28 search requests every time the same all-state list is asked.
_STATE_CACHE: dict[str, tuple[float, list[dict]]] = {}
_STATE_CACHE_TTL_SECONDS = 12 * 60 * 60


def _normalized(query: str) -> str:
    return f" {re.sub(r'\s+', ' ', query.casefold()).strip()} "


def is_all_india_state_cm_query(query: str) -> bool:
    normalized = _normalized(query)

    if any(term in normalized for term in ALL_STATE_CM_TERMS):
        return True
    if ALL_STATE_CM_REGEX.search(query):
        return True

    # V48.1: Roman-Hindi shorthand such as
    # "ind ke saare cm ki list do 2026 ki" must use the existing
    # per-state verification path rather than generic web research.
    india_scope = any(
        term in normalized
        for term in (
            " india ",
            " indian ",
            " ind ",
            " bharat ",
            " hindustan ",
            " भारत ",
            " इंडिया ",
        )
    )
    cm_scope = any(
        term in normalized
        for term in (
            " cm ",
            " cms ",
            " chief minister",
            " chief ministers",
            " mukhyamantri",
            " मुख्यमंत्री",
            " सीएम",
        )
    )
    all_scope = any(
        term in normalized
        for term in (
            " all ",
            " sabhi ",
            " sare ",
            " saare ",
            " poore ",
            " pure ",
            " complete ",
            " पूरी ",
            " सभी ",
            " सारे ",
        )
    )
    list_scope = any(
        term in normalized
        for term in (
            " cm list ",
            " cms list ",
            " cm ki list ",
            " cm ke list ",
            " list of cm ",
            " list of cms ",
            " सूची ",
        )
    )

    return bool(india_scope and cm_scope and (all_scope or list_scope))


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
        or any(term in normalized for term in DYNAMIC_FACT_TERMS)
        or _is_officeholder_query(query)
        or is_all_india_state_cm_query(query)
    )


def _host(url: str) -> str:
    return urlparse(url).netloc.casefold().split(":", 1)[0].removeprefix("www.")


def _source_kind(url: str) -> str:
    host = _host(url)
    if host.endswith(".gov.in") or host.endswith(".nic.in") or host in {
        "india.gov.in", "pmindia.gov.in", "pib.gov.in"
    }:
        return "official"
    if host.endswith(".gov") or host.endswith(".go.uk") or host.endswith(".europa.eu"):
        return "official"
    if _domain_matches(host, PRIMARY_PLATFORM_DOMAINS):
        return "primary_platform"
    if host.endswith(".edu") or host.endswith(".ac.in"):
        return "academic"
    if _domain_matches(host, TRUSTED_REFERENCE_DOMAINS):
        return "trusted_reference"
    if any(host == item or host.endswith("." + item) for item in REPUTABLE_NEWS_HOSTS):
        return "reputable_news"
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
    kind_rank = {
        "official": 0,
        "primary_platform": 1,
        "academic": 1,
        "trusted_reference": 2,
        "reputable_news": 3,
        "other": 4,
    }.get(kind, 4)
    published = _parse_date(item.get("published_date"))
    score = float(item.get("score") or 0.0)
    return kind_rank, -published, -score


def _clean_result(item: dict, *, entity: str | None = None, content_limit: int = 2400) -> dict:
    content = (item.get("raw_content") or item.get("content") or item.get("text") or "").strip()
    content = re.sub(r"\n{3,}", "\n\n", content)[:content_limit]
    url = (item.get("url") or "").strip()
    return {
        "title": item.get("title") or "Source",
        "url": url,
        "domain": _host(url),
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
    """Run topic-aware research and return ranked, deduplicated evidence."""
    as_of = as_of or date.today().isoformat()

    if is_all_india_state_cm_query(query):
        return await search_all_india_state_cms(settings, as_of)

    profile = classify_research_profile(query)
    profile_instruction = ""
    if profile:
        primary = ", ".join(profile.primary_domains)
        reference = ", ".join(profile.reference_domains)
        profile_instruction = (
            f" This is a {profile.label} question. First check official/primary platforms: "
            f"{primary}. Then cross-check with trusted specialist sources: {reference}."
        )

    base_query = (
        f"As of {as_of}, verify the newest currently valid answer to this question: {query}. "
        "Use primary sources where possible. Treat newer official updates, corrections, releases, "
        "rankings, subscriber counts, availability changes, appointments and dated reports as "
        "overriding older pages."
        if require_current
        else (
            f"Research this question carefully: {query}. Prefer primary/official sources, then "
            "cross-check important claims with trusted specialist sources."
        )
    ) + profile_instruction

    jobs: list = [
        tavily_search(
            base_query,
            settings,
            max_results=min(max_results, 7),
            topic="general",
            search_depth="basic",
            content_limit=1800,
        )
    ]

    if profile:
        if profile.primary_domains:
            jobs.append(
                tavily_search(
                    base_query,
                    settings,
                    max_results=min(max_results, 7),
                    topic="general",
                    include_domains=profile.primary_domains[:14],
                    search_depth="basic",
                    content_limit=1800,
                )
            )
        if profile.reference_domains:
            jobs.append(
                tavily_search(
                    base_query,
                    settings,
                    max_results=min(max_results, 7),
                    topic="general",
                    include_domains=profile.reference_domains[:14],
                    search_depth="basic",
                    content_limit=1700,
                )
            )

    if require_current:
        jobs.append(
            tavily_search(
                base_query,
                settings,
                max_results=min(max_results, 7),
                topic="news",
                time_range="year",
                search_depth="basic",
                content_limit=1500,
            )
        )

    if _is_india_query(query) and _is_officeholder_query(query):
        jobs.append(
            tavily_search(
                base_query,
                settings,
                max_results=min(max_results, 8),
                topic="general",
                include_domains=OFFICIAL_INDIA_DOMAINS,
                search_depth="basic",
                content_limit=1700,
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
                ranked
                + await exa_search(
                    base_query,
                    settings,
                    max_results=max_results,
                    content_limit=1800,
                ),
                max_results,
            )
        except Exception as exc:
            errors.append(f"exa: {exc}")

    if ranked:
        profile_name = profile.key if profile else "general"
        providers = "tavily+exa" if settings.exa_api else "tavily"
        return ranked, f"domain-router:{profile_name}:{providers}"
    return [], "; ".join(errors) if errors else "No research API configured"

