from __future__ import annotations

import re
import unicodedata
from typing import Any


# Facts in these categories can change suddenly and are especially dangerous
# to answer from stale model knowledge or old shared memory.
_VOLATILE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:died|dead|death|passed\s+away|cause\s+of\s+death|"
        r"alive|still\s+alive|is\s+alive|when\s+did\s+.+\s+die)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:death\s+kab|death\s+kaise|kab\s+(?:mare|mara|mari|mar[e]?|"
        r"mar\s+gaye)|kaise\s+(?:mare|mara|mari|mar[e]?|mar\s+gaye)|"
        r"zinda\s+(?:hai|he)|jinda\s+(?:hai|he)|mar\s+chuke|"
        r"nidhan|mrityu|maut)\b",
        re.I,
    ),
    re.compile(
        r"(?:\u0928\u093f\u0927\u0928|"
        r"\u092e\u0943\u0924\u094d\u092f\u0941|"
        r"\u092e\u094c\u0924|"
        r"\u0926\u0947\u0939\u093e\u0902\u0924|"
        r"\u091c\u0940\u0935\u093f\u0924|"
        r"\u091c\u093c\u093f\u0902\u0926\u093e|"
        r"\u091c\u093f\u0902\u0926\u093e|"
        r"\u092e\u0930\s+\u0917\u090f|"
        r"\u092e\u0930\s+\u091a\u0941\u0915\u0947|"
        r"\u0915\u092c\s+\u092e\u0930\u0947|"
        r"\u0915\u0948\u0938\u0947\s+\u092e\u0930\u0947|"
        r"\u0915\u0948\u0938\u0947\s+\u0939\u0941\u0908)",
        re.I,
    ),
    re.compile(
        r"\b(?:hospitali[sz]ed|admitted\s+to\s+hospital|critical\s+condition|"
        r"icu|seriously\s+ill|health\s+condition|health\s+update)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:arrested|detained|released\s+from\s+(?:jail|custody)|"
        r"bail|missing|found\s+missing)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:resign(?:ed|ation)?|appoint(?:ed|ment)?|sworn\s+in|"
        r"retire(?:d|ment)?|suspended|removed\s+from\s+office|"
        r"stepped\s+down|joined\s+.+\s+as|left\s+.+\s+role)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:shaadi|shadi|married|marriage|divorced|divorce|engaged|"
        r"separated)\b",
        re.I,
    ),
)


def is_volatile_person_status_query(query: str) -> bool:
    value = unicodedata.normalize(
        "NFC",
        re.sub(r"\s+", " ", str(query or "")).strip(),
    )
    if len(value) < 3:
        return False
    return any(pattern.search(value) for pattern in _VOLATILE_PATTERNS)


def build_fresh_fact_search_query(
    query: str,
    *,
    as_of: str,
) -> str:
    original = re.sub(r"\s+", " ", str(query or "")).strip()
    return (
        f"As of {as_of}, verify this potentially time-sensitive public-person "
        f"status question using the newest reliable evidence: {original}. "
        "If the question concerns death or whether someone is alive, explicitly "
        "check for confirmed death reports, family/representative statements, "
        "official records where available, funeral/obituary reporting, and recent "
        "reputable coverage. Distinguish confirmed death from false death rumours. "
        "Do not infer that a person is alive merely because an older biography or "
        "profile page exists. If deceased, give the exact date, place, and cause "
        "only when directly supported by reliable sources. If sources conflict, "
        "report the conflict instead of guessing. Prefer primary/official sources "
        "and multiple independent reputable news organisations."
    )


def fresh_fact_answer_policy(
    query: str,
    *,
    as_of: str,
) -> str:
    if not is_volatile_person_status_query(query):
        return ""

    return (
        "VASUKI V58 FRESH FACTS GUARD:\n"
        f"As-of date: {as_of}.\n"
        "This request concerns a fact that can change suddenly. Use the supplied "
        "live evidence, not stale model knowledge, cached biography text, or old "
        "memory, as the authority.\n"
        "For death/alive claims: require explicit recent evidence. Never conclude "
        "'alive' only because no death record was found in an old source. Never "
        "state a death date or cause unless the evidence explicitly supports it.\n"
        "For appointment/resignation/arrest/hospitalisation/retirement and similar "
        "status changes: prefer the newest official or primary statement, then "
        "cross-check with independent reputable reporting.\n"
        "If evidence is insufficient or materially conflicting, say that the "
        "current status could not be safely verified instead of guessing."
    )


def health_snapshot() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v58",
        "name": "Vasuki Fresh Facts Guard",
        "features": [
            "death-and-alive-live-verification",
            "roman-hindi-life-status-detection",
            "hindi-life-status-detection",
            "hospitalisation-status-verification",
            "arrest-and-release-status-verification",
            "appointment-resignation-retirement-verification",
            "relationship-status-freshness-routing",
            "no-alive-from-absence-inference",
            "fail-closed-on-insufficient-evidence",
        ],
        "hardcoded_people": False,
        "new_database_migration_required": False,
        "new_api_key_required": False,
        "extra_provider_call_for_nonvolatile_questions": False,
    }

