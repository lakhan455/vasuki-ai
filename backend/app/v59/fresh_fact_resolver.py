from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.v58.fresh_facts import is_volatile_person_status_query


@dataclass(frozen=True, slots=True)
class FreshFactPlan:
    kind: str
    subject: str
    queries: tuple[str, ...]


_DEATH_TERMS = re.compile(
    r"(?:\bdied\b|\bdead\b|\bdeath\b|\bpassed\s+away\b|"
    r"\bcause\s+of\s+death\b|\balive\b|\bstill\s+alive\b|"
    r"\bzinda\b|\bjinda\b|\bmar\s+chuke\b|\bnidhan\b|"
    r"\bmrityu\b|\bmaut\b|"
    r"\u0928\u093f\u0927\u0928|"
    r"\u092e\u0943\u0924\u094d\u092f\u0941|"
    r"\u092e\u094c\u0924|"
    r"\u0926\u0947\u0939\u093e\u0902\u0924|"
    r"\u091c\u0940\u0935\u093f\u0924|"
    r"\u091c\u093c\u093f\u0902\u0926\u093e|"
    r"\u091c\u093f\u0902\u0926\u093e)",
    re.I,
)

_HEALTH_TERMS = re.compile(
    r"\b(?:hospitali[sz]ed|hospital|icu|critical|health\s+condition|"
    r"health\s+update|seriously\s+ill)\b",
    re.I,
)

_LEGAL_TERMS = re.compile(
    r"\b(?:arrested|detained|custody|bail|released|missing)\b",
    re.I,
)

_ROLE_TERMS = re.compile(
    r"\b(?:resign(?:ed|ation)?|appoint(?:ed|ment)?|sworn\s+in|"
    r"retire(?:d|ment)?|suspended|removed\s+from\s+office|"
    r"stepped\s+down)\b",
    re.I,
)

_RELATIONSHIP_TERMS = re.compile(
    r"\b(?:married|marriage|divorced|divorce|engaged|separated|"
    r"shaadi|shadi)\b",
    re.I,
)

_STRIP_PHRASES = (
    # English
    r"\bwhen\s+did\b",
    r"\bhow\s+did\b",
    r"\bcause\s+of\s+death\b",
    r"\bpassed\s+away\b",
    r"\bstill\s+alive\b",
    r"\bis\s+alive\b",
    r"\bdeath\b",
    r"\bdied\b",
    r"\bdead\b",
    r"\balive\b",
    r"\bwhen\b",
    r"\bhow\b",
    r"\bwhat\b",
    r"\bwas\b",
    r"\bis\b",
    r"\bdid\b",
    r"\bthe\b",
    # Roman Hindi
    r"\bdeath\s+kab\s+hui\b",
    r"\bdeath\s+kaise\s+hui\b",
    r"\bkab\s+hui\b",
    r"\bkaise\s+hui\b",
    r"\bkab\s+mare\b",
    r"\bkaise\s+mare\b",
    r"\bzinda\s+hai\b",
    r"\bzinda\s+he\b",
    r"\bjinda\s+hai\b",
    r"\bjinda\s+he\b",
    r"\bmar\s+chuke\b",
    r"\bnidhan\b",
    r"\bmrityu\b",
    r"\bmaut\b",
    r"\bkya\b",
    r"\baur\b",
    r"\bor\b",
    r"\bhui\b",
    r"\bhua\b",
    r"\bhai\b",
    r"\bhe\b",
    # Hindi
    r"\u0915\u0940",
    r"\u0915\u093e",
    r"\u0915\u0947",
    r"\u092e\u0943\u0924\u094d\u092f\u0941",
    r"\u0928\u093f\u0927\u0928",
    r"\u092e\u094c\u0924",
    r"\u0926\u0947\u0939\u093e\u0902\u0924",
    r"\u0915\u092c",
    r"\u0915\u0948\u0938\u0947",
    r"\u0939\u0941\u0908",
    r"\u0939\u0941\u0906",
    r"\u0914\u0930",
    r"\u0915\u094d\u092f\u093e",
    r"\u091c\u0940\u0935\u093f\u0924",
    r"\u091c\u093c\u093f\u0902\u0926\u093e",
    r"\u091c\u093f\u0902\u0926\u093e",
    r"\u0939\u0948\u0902",
    r"\u0939\u0948",
    r"\u092e\u0930\u0947",
    r"\u092e\u0930",
    r"\u091a\u0941\u0915\u0947",
    r"\u0917\u090f",
)

_DEATH_POSITIVE = re.compile(
    r"(?:\bhas\s+died\b|\bdied\s+(?:at|on|in|after|aged|from|due)\b|"
    r"\bpassed\s+away\b|\bpronounced\s+dead\b|\bdeclared\s+dead\b|"
    r"\bcremated\b|\bfuneral\b|\blast\s+rites\b|\bobituary\b|"
    r"\bdeath\s+was\s+confirmed\b|\bconfirmed\s+(?:his|her|their)\s+death\b)",
    re.I,
)

_DEATH_NEGATIVE = re.compile(
    r"(?:\bdeath\s+hoax\b|\bfalse\s+(?:death\s+)?(?:report|reports|rumou?r|rumou?rs)\b|"
    r"\bfake\s+(?:death\s+)?news\b|\bnot\s+dead\b|\balive\s+and\s+well\b|"
    r"\bdenied\s+(?:the\s+)?death\b|\bdeath\s+rumou?rs?\s+(?:are|were)\s+false\b)",
    re.I,
)

_ALIVE_POSITIVE = re.compile(
    r"(?:\balive\s+and\s+well\b|\bis\s+alive\b|\bstill\s+alive\b|"
    r"\bnot\s+dead\b|\bdeath\s+hoax\b|\bdeath\s+rumou?rs?\s+(?:are|were)\s+false\b)",
    re.I,
)


def _normalized(value: str) -> str:
    return unicodedata.normalize(
        "NFC",
        re.sub(r"\s+", " ", str(value or "")).strip(),
    )


def fresh_fact_kind(query: str) -> str:
    value = _normalized(query)
    if _DEATH_TERMS.search(value):
        return "death_alive"
    if _HEALTH_TERMS.search(value):
        return "health"
    if _LEGAL_TERMS.search(value):
        return "legal_status"
    if _ROLE_TERMS.search(value):
        return "role_status"
    if _RELATIONSHIP_TERMS.search(value):
        return "relationship"
    return "other"


def extract_fresh_fact_subject(query: str) -> str:
    value = _normalized(query)
    cleaned = value
    for pattern in _STRIP_PHRASES:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.I)

    # Remove punctuation while preserving Unicode names and common name separators.
    cleaned = re.sub(r"[?!.:,;()\[\]{}\"'`]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")

    # If stripping was too aggressive, retain the original query rather than
    # searching an empty subject.
    return cleaned if len(cleaned) >= 2 else value


def build_fresh_fact_plan(
    query: str,
    *,
    as_of: str,
) -> FreshFactPlan:
    kind = fresh_fact_kind(query)
    subject = extract_fresh_fact_subject(query)
    year = str(as_of or "")[:4]

    if kind == "death_alive":
        queries = (
            f'{subject} died death obituary {year}'.strip(),
            f'{subject} death confirmed family statement funeral {year}'.strip(),
            f'{subject} alive death hoax latest {year}'.strip(),
        )
    elif kind == "health":
        queries = (
            f'{subject} hospitalized health condition latest {year}'.strip(),
            f'{subject} hospital ICU official statement {year}'.strip(),
            f'{subject} latest health update {year}'.strip(),
        )
    elif kind == "legal_status":
        queries = (
            f'{subject} arrested detained bail released latest {year}'.strip(),
            f'{subject} police court official statement {year}'.strip(),
            f'{subject} custody status latest {year}'.strip(),
        )
    elif kind == "role_status":
        queries = (
            f'{subject} resigned appointed retired latest {year}'.strip(),
            f'{subject} official appointment resignation retirement {year}'.strip(),
            f'{subject} current role latest {year}'.strip(),
        )
    elif kind == "relationship":
        queries = (
            f'{subject} married divorce engaged latest {year}'.strip(),
            f'{subject} marriage divorce confirmation {year}'.strip(),
            f'{subject} relationship status latest {year}'.strip(),
        )
    else:
        queries = (
            f'{subject} latest verified status {year}'.strip(),
        )

    # Stable de-duplication.
    unique: list[str] = []
    seen: set[str] = set()
    for item in queries:
        key = item.casefold()
        if item and key not in seen:
            seen.add(key)
            unique.append(item)

    return FreshFactPlan(
        kind=kind,
        subject=subject,
        queries=tuple(unique),
    )


def _domain(item: dict[str, Any]) -> str:
    value = str(item.get("domain") or "").strip().casefold()
    if value:
        return value.removeprefix("www.")
    url = str(item.get("url") or "").strip()
    try:
        host = urlparse(url).hostname
    except Exception:
        host = None
    return host.casefold().removeprefix("www.") if host else ""


def _source_text(item: dict[str, Any]) -> str:
    return (
        str(item.get("title") or "")
        + "\n"
        + str(item.get("content") or "")[:2600]
    )


def _credible(item: dict[str, Any]) -> bool:
    source_type = str(item.get("source_type") or "").strip().casefold()
    if source_type in {
        "official",
        "primary_platform",
        "trusted_reference",
        "reputable_news",
        "academic",
    }:
        return True

    domain = _domain(item)
    return any(
        domain == trusted or domain.endswith("." + trusted)
        for trusted in (
            "reuters.com",
            "apnews.com",
            "bbc.com",
            "bbc.co.uk",
            "theguardian.com",
            "indianexpress.com",
            "hindustantimes.com",
            "indiatoday.in",
            "ndtv.com",
            "timesofindia.indiatimes.com",
            "aljazeera.com",
            "theprint.in",
            "moneycontrol.com",
            "livemint.com",
            "business-standard.com",
        )
    )


def fresh_fact_evidence_context(
    query: str,
    sources: list[dict[str, Any]],
    *,
    as_of: str,
) -> str:
    if not is_volatile_person_status_query(query):
        return ""

    plan = build_fresh_fact_plan(query, as_of=as_of)
    credible_sources = [item for item in sources if _credible(item)]
    domains = {_domain(item) for item in credible_sources if _domain(item)}

    lines = [
        "VASUKI V59 FRESH FACT RESOLVER:",
        f"Status kind={plan.kind}; subject={plan.subject!r}; as_of={as_of}.",
        (
            f"Live evidence received from {len(credible_sources)} credible source(s) "
            f"across {len(domains)} independent domain(s)."
        ),
    ]

    if plan.kind == "death_alive":
        death_domains: set[str] = set()
        alive_domains: set[str] = set()

        for item in credible_sources:
            text = _source_text(item)
            domain = _domain(item)
            if not domain:
                continue

            has_negative = bool(_DEATH_NEGATIVE.search(text))
            if _DEATH_POSITIVE.search(text) and not has_negative:
                death_domains.add(domain)

            if _ALIVE_POSITIVE.search(text):
                alive_domains.add(domain)

        if len(death_domains) >= 2 and len(death_domains) > len(alive_domains):
            lines.extend(
                [
                    "RESOLUTION=CONFIRMED_DECEASED_EVIDENCE",
                    (
                        "Multiple independent credible live sources explicitly report death. "
                        "Do NOT answer that no reliable death evidence exists and do NOT answer "
                        "that the person is alive."
                    ),
                    (
                        "State the death as confirmed. Extract date, place and cause only from "
                        "the supplied source text; if a detail differs across sources, explain "
                        "the difference instead of inventing certainty."
                    ),
                ]
            )
        elif len(alive_domains) >= 2 and len(alive_domains) >= len(death_domains):
            lines.extend(
                [
                    "RESOLUTION=EXPLICIT_ALIVE_OR_HOAX_EVIDENCE",
                    (
                        "Multiple credible live sources explicitly indicate the person is alive "
                        "or that death reports are false. Do not report a death without stronger "
                        "newer contrary evidence."
                    ),
                ]
            )
        else:
            lines.extend(
                [
                    "RESOLUTION=UNRESOLVED_LIFE_STATUS",
                    (
                        "Evidence is not strong enough for a deterministic life-status resolution. "
                        "Compare the supplied sources carefully and fail closed if still uncertain."
                    ),
                ]
            )
    else:
        lines.extend(
            [
                "RESOLUTION=LIVE_STATUS_EVIDENCE_REQUIRED",
                (
                    "Use the newest credible evidence for this changing status. If evidence is "
                    "insufficient or conflicting, say so instead of relying on model memory."
                ),
            ]
        )

    return "\n".join(lines)


def health_snapshot() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v59",
        "name": "Vasuki Fresh Fact Resolver",
        "features": [
            "volatile-status-query-expansion",
            "roman-hindi-subject-extraction",
            "hindi-subject-extraction",
            "multi-query-live-retrieval",
            "credible-source-cross-check",
            "death-hoax-negation-detection",
            "confirmed-death-evidence-resolution",
            "fail-closed-context-propagation",
        ],
        "hardcoded_people": False,
        "new_database_migration_required": False,
        "new_api_key_required": False,
        "extra_provider_call_required": False,
    }
