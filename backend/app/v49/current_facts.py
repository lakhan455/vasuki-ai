# VASUKI_V49_2_6_CANDIDATE_QUALITY_GUARD_FIX
# VASUKI_V49_2_5_ALIAS_ADJUDICATION_FIX
# VASUKI_V49_2_4_HONORIFIC_FILTER_FIX
# VASUKI_V49_2_3_OFFICIAL_CM_MARKUP_FIX
# VASUKI_V49_2_2_CM_PREFIX_DEDUPE_FIX
# VASUKI_V49_2_1_EXTRACTOR_BOUNDARY_FIX
# VASUKI_V49_2_EVIDENCE_PIPELINE_FIX
# VASUKI_V49_1_6_AST_SAFE_FINAL_FIX
# VASUKI_V49_1_3_ROBUST_EXTRACTOR_FIX
from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.research import (
    INDIA_STATES,
    _dedupe_and_rank,
    exa_search,
    search_all_india_state_cms,
    tavily_search,
)


CM_SNAPSHOT_MARKER = "VASUKI_V49_1_VERIFIED_28_CM"
_NEGATIVE_ROLE_TERMS = (
    "deputy chief minister",
    "deputy cm",
    "leader of opposition",
    "opposition leader",
    "former chief minister",
    "former cm",
    "ex chief minister",
    "ex-cm",
    "chief ministerial candidate",
    "cm candidate",
    "party president",
)


@dataclass(slots=True)
class StateCmFact:
    state: str
    chief_minister: str
    confidence: float
    evidence_urls: list[str]
    evidence: list[dict[str, Any]]


@dataclass(slots=True)
class VerifiedCmSnapshot:
    stored_answer: str
    display_answer: str
    sources: list[dict[str, Any]]
    evidence_urls: list[str]
    search_provider: str
    verifier_provider: str
    confidence: float
    verified_entities: int


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _name_tokens(value: str) -> list[str]:
    return [token for token in _normalise(value).split() if len(token) > 1]


def _token_coverage(name: str, text: str) -> float:
    tokens = _name_tokens(name)
    if not tokens:
        return 0.0
    haystack = set(_normalise(text).split())
    matched = sum(1 for token in tokens if token in haystack)
    return matched / len(tokens)


def _role_window_supports(name: str, item: dict[str, Any]) -> bool:
    title = str(item.get("title") or "")
    content = str(item.get("content") or "")
    url = str(item.get("url") or "")

    disqualifying = re.compile(
        r"\b(?:deputy|former|ex)\s+chief\s+minister\b|"
        r"\bleader\s+of\s+(?:the\s+)?opposition\b|"
        r"\bopposition\s+leader\b|"
        r"\bchief\s+ministerial\s+candidate\b",
        re.I,
    )

    if disqualifying.search(title):
        return False

    raw = " ".join([title, content])
    if _token_coverage(name, raw) < 0.75:
        return False

    target = _normalise(name)
    candidates = {
        _normalise(candidate)
        for candidate in _candidate_names_from_item(item)
        if candidate
    }
    if target in candidates:
        return True

    if str(item.get("source_type") or "") == "official":
        if disqualifying.search(content[:320]):
            return False

        role_hint = bool(
            re.search(
                r"(?:hon'?ble|honorable|honourable)?\s*chief\s+minister\b",
                title,
                re.I,
            )
            or re.search(
                r"(?:chief[-_/ ]minister|about[-_/ ]chief[-_/ ]minister|"
                r"/cm(?:/|$)|cm[-_/ ])",
                url,
                re.I,
            )
        )
        if role_hint:
            return True

    return False




def _positive_evidence(name: str, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    positive: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in evidence:
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        if _role_window_supports(name, item):
            positive.append(item)
            seen.add(url)
    return positive


def _evidence_quality_ok(items: list[dict[str, Any]]) -> bool:
    if not items:
        return False
    if any(str(item.get("source_type") or "") == "official" for item in items):
        return True
    trusted = [
        item for item in items
        if str(item.get("source_type") or "")
        in {"reputable_news", "trusted_reference", "primary_platform"}
    ]
    return len({str(item.get("url") or "") for item in trusted}) >= 2


# VASUKI_V49_1_1_DETERMINISTIC_CM_ADJUDICATION_START
_NAME_WORD = r"(?:[A-Z]\.|[A-Z][A-Za-z'’.-]{1,30})"
_NAME_EXPR = rf"({_NAME_WORD}(?:\s+{_NAME_WORD}){{0,5}})"
_NAME_PATTERNS = (
    re.compile(
        rf"\b{_NAME_EXPR}\s+(?:is|serves\s+as|continues\s+as|continues\s+to\s+be|"
        rf"was\s+sworn\s+in\s+as|sworn\s+in\s+as|took\s+oath\s+as|"
        rf"was\s+appointed\s+as|appointed\s+as)\s+(?:the\s+)?(?:current\s+)?"
        rf"(?:Hon'?ble\s+)?Chief\s+Minister\b"
    ),
    re.compile(
        rf"\b(?:Hon'?ble\s+)?Chief\s+Minister(?:\s+of\s+[A-Z][A-Za-z &.'-]{{1,50}})?"
        rf"\s*(?:is|:|[-–—]|,)\s*(?:Shri|Smt|Dr\.?|Mr\.?|Ms\.?)?\s*{_NAME_EXPR}\b"
    ),
    re.compile(
        rf"\b(?:Hon'?ble\s+)?Chief\s+Minister\s+(?:Shri|Smt|Dr\.?|Mr\.?|Ms\.?)\s+{_NAME_EXPR}\b"
    ),
    re.compile(
        rf"\b(?:Shri|Smt|Dr\.?|Mr\.?|Ms\.?)\s+{_NAME_EXPR}\s*,?\s*"
        rf"(?:Hon'?ble\s+)?Chief\s+Minister\b"
    ),
    re.compile(rf"\b{_NAME_EXPR}\s*,\s*(?:Hon'?ble\s+)?Chief\s+Minister\b"),
)

_BAD_NAME_WORDS = {
    "chief", "minister", "government", "state", "india", "department", "office",
    "honble", "honourable", "honorable", "shri", "smt", "mr", "ms", "dr",
    "deputy", "leader", "opposition", "former", "party", "president", "cabinet",
    "secretariat", "portal", "official", "website",
}


def _clean_candidate_name(value: str) -> str:
    value = re.sub(
        r"^(?:Hon'?ble|Shri|Smt|Dr\.?|Mr\.?|Ms\.?)\s+",
        "",
        str(value or "").strip(),
    )
    value = re.sub(r"\s+", " ", value).strip(" ,:;|–—-")
    tokens = _name_tokens(value)
    if not tokens or len(tokens) > 6:
        return ""
    if any(token in _BAD_NAME_WORDS for token in tokens):
        return ""
    if len(value) < 3 or len(value) > 120:
        return ""
    return value


def _candidate_names_from_item(item: dict[str, Any]) -> list[str]:
    """Extract a current Chief Minister name from real web snippets.

    V49.2.4 fixes honorific-only false candidates such as "Hon’ble".
    """
    title = str(item.get("title") or "")
    content = str(item.get("content") or "")
    url = str(item.get("url") or "")
    entity = str(item.get("entity") or "")
    source_type = str(item.get("source_type") or "")

    name_word = r"(?:[A-Z]\.|[A-Z][A-Za-z'’.-]{1,35}|[A-Z]{2,35})"
    name_expr = rf"(?P<name>{name_word}(?:[ \t]+{name_word}){{0,5}})"
    name_re = re.compile(name_expr)
    honorific_name_re = re.compile(
        rf"(?i:(?:Shri|Smt|Sri|Dr\.?|Mr\.?|Ms\.?))[ \t]+{name_expr}"
    )

    current_role_re = re.compile(
        r"(?<!deputy[ \t])(?<!former[ \t])(?<!ex[ \t])"
        r"(?:(?:hon(?:'|’)?ble|honorable|honourable)[ \t]+)?"
        r"chief[ \t]+minister\b|"
        r"(?<!deputy[ \t])\bCM\b",
        re.I,
    )
    disqualifying_role_re = re.compile(
        r"\b(?:deputy|former|ex)[ \t]+chief[ \t]+minister\b|"
        r"\bleader[ \t]+of[ \t]+(?:the[ \t]+)?opposition\b|"
        r"\bopposition[ \t]+leader\b|"
        r"\bchief[ \t]+ministerial[ \t]+candidate\b",
        re.I,
    )

    bad_tokens = {
        "chief", "minister", "government", "state", "india", "department",
        "office", "official", "portal", "website", "council", "cabinet",
        "home", "page", "profile", "biography", "honble", "hon", "ble",
        "honourable", "honorable", "deputy", "former", "opposition",
        "leader", "party", "president", "secretariat", "current",
        "serving", "today", "latest", "welcome", "image", "photo",
    }

    def strip_markup(line: str) -> str:
        value = str(line or "").strip()
        value = re.sub(r"^[#>*•\-–—|: \t]+", "", value)
        value = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", value)
        value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
        value = re.sub(r"(?i)^image[ \t]*:[ \t]*", "", value)
        return value.strip()

    def clean(value: str) -> str:
        value = strip_markup(value)

        # Strip both role-adjacent honorifics and normal personal honorifics.
        # If the value is only "Hon’ble", this becomes empty and is rejected.
        value = re.sub(
            r"^(?:CM|C\.M\.|Shri|Smt|Sri|Dr\.?|Mr\.?|Ms\.?|"
            r"Hon(?:'|’)?ble|Honorable|Honourable)[ \t]*",
            "",
            value,
            flags=re.I,
        )

        value = re.sub(r"[ \t]+", " ", value).strip(" ,:;|–—-")
        if not value:
            return ""

        normalized_value = _normalise(value)
        if normalized_value in {
            "hon ble",
            "honble",
            "honorable",
            "honourable",
            "chief minister",
            "cm",
        }:
            return ""

        tokens = _name_tokens(value)
        if not tokens or len(tokens) > 6:
            return ""
        if any(token in bad_tokens for token in tokens):
            return ""
        if entity:
            entity_tokens = set(_name_tokens(entity))
            if entity_tokens and set(tokens).issubset(entity_tokens):
                return ""
        if len(value) < 3 or len(value) > 120:
            return ""
        return value

    found: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        candidate = clean(value)
        key = _normalise(candidate)
        if candidate and key and key not in seen:
            seen.add(key)
            found.append(candidate)

    # 1) Explicit role occurrences inside content.
    for role_match in current_role_re.finditer(content):
        start, end = role_match.span()
        local = content[max(0, start - 28):min(len(content), end + 28)]
        if disqualifying_role_re.search(local):
            continue

        before = content[max(0, start - 180):start]
        after = content[end:min(len(content), end + 180)]

        before = re.sub(
            r"(?i)\b(?:is|serves[ \t]+as|continues[ \t]+as|"
            r"continues[ \t]+to[ \t]+be|was[ \t]+sworn[ \t]+in[ \t]+as|"
            r"sworn[ \t]+in[ \t]+as|took[ \t]+oath[ \t]+as|"
            r"was[ \t]+appointed[ \t]+as|appointed[ \t]+as|"
            r"the|current|serving)[ \t]*$",
            "",
            before,
        )
        before_line = strip_markup(
            before.splitlines()[-1] if before.splitlines() else before
        )
        before_candidates = [
            m.group("name")
            for m in name_re.finditer(before_line)
        ]
        if before_candidates:
            add(before_candidates[-1])

        after_first_line = strip_markup(
            after.splitlines()[0] if after.splitlines() else after
        )
        if entity:
            after_first_line = re.sub(
                rf"(?i)^[ \t]*(?:of[ \t]+{re.escape(entity)}[ \t]*)",
                "",
                after_first_line,
            )
        after_first_line = re.sub(
            r"(?i)^[ \t]*(?:of[ \t]+[A-Z][A-Za-z &.'-]{1,60}[ \t]*)?"
            r"(?:is[ \t]+|[:|,\-–—][ \t]*)?"
            r"(?:(?:Shri|Smt|Sri|Dr\.?|Mr\.?|Ms\.?)[ \t]+)?",
            "",
            after_first_line,
        )
        match = name_re.match(after_first_line.lstrip(" \t"))
        if match:
            add(match.group("name"))

        window = content[max(0, start - 120):min(len(content), end + 180)]
        for line in window.splitlines():
            line = strip_markup(line)
            match = honorific_name_re.search(line)
            if match:
                add(match.group("name"))

    # 2) Official CM/profile/biography page layouts.
    role_hint = bool(
        current_role_re.search(title)
        or current_role_re.search(content[:500])
        or re.search(
            r"(?:chief[-_/ ]minister|about[-_/ ]chief[-_/ ]minister|"
            r"/cm(?:/|$)|cm[-_/ ])",
            url,
            re.I,
        )
    )
    title_disqualified = bool(disqualifying_role_re.search(title))

    if source_type == "official" and role_hint and not title_disqualified:
        head_lines = [strip_markup(x) for x in content[:1400].splitlines()]
        head_lines = [x for x in head_lines if x]

        if not disqualifying_role_re.search(" ".join(head_lines[:4])):
            for index, line in enumerate(head_lines[:18]):
                if not line:
                    continue
                if re.match(r"(?i)^(?:image|photo)\b", line):
                    continue
                if current_role_re.fullmatch(line):
                    continue
                if disqualifying_role_re.search(line):
                    continue

                honorific_match = honorific_name_re.search(line)
                if honorific_match:
                    add(honorific_match.group("name"))
                    if found:
                        break

                plain_match = name_re.fullmatch(line)
                next_line = (
                    head_lines[index + 1]
                    if index + 1 < len(head_lines)
                    else ""
                )
                if plain_match and (
                    current_role_re.search(next_line)
                    or index <= 6
                ):
                    add(plain_match.group("name"))
                    if found:
                        break

    return found






def _source_date_score(item: dict[str, Any]) -> float:
    value = str(item.get("published_date") or "").strip()
    if not value:
        return 0.0
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return 0.0


def _deterministic_fact(
    state: str,
    evidence: list[dict[str, Any]],
    *,
    min_confidence: float,
) -> StateCmFact | None:
    """Resolve one current CM while filtering non-person UI/page fragments.

    V49.2.6 keeps the alias consolidation from V49.2.5 but adds a generic
    candidate-quality guard. Real pages can expose capitalized fragments such
    as "Tenure", "Homepage", "Designation", "Press Releases" etc. Those are
    not people and must never compete with a real office-holder.
    """

    raw_candidates: dict[str, str] = {}
    for item in evidence:
        for name in _candidate_names_from_item(item):
            key = _normalise(name)
            if key:
                raw_candidates.setdefault(key, name)

    if not raw_candidates:
        return None

    all_names = list(raw_candidates.values())

    # Generic page/UI/discourse terms that frequently become false positive
    # "names" when parsing government portals or news markup.
    non_person_tokens = {
        "act", "according", "address", "addressing", "biography", "birth",
        "board", "cabinet", "chief", "children", "constituency", "contact",
        "current", "date", "department", "deputy", "designation", "details",
        "district", "during", "education", "email", "father", "first",
        "former", "fund", "government", "governance", "governor", "he",
        "home", "homepage", "hometown", "image", "important", "india",
        "latest", "leader", "links", "media", "message", "minister", "mla",
        "mlas", "mother", "news", "office", "official", "opposition", "page",
        "party", "photo", "place", "portal", "president", "press", "profile",
        "qualification", "rakhi", "release", "releases", "relief", "second",
        "secretariat", "service", "serving", "she", "social", "source",
        "spouse", "state", "tenure", "today", "website", "welcome", "with",
        "years", "youtube", "bjp", "at", "the", "of", "and",
    }

    def alias_tokens(value: str) -> list[str]:
        return [token for token in _normalise(value).split() if token]

    longer_name_sets = [
        set(alias_tokens(name))
        for name in all_names
        if len(alias_tokens(name)) >= 2
    ]

    def plausible_person_candidate(name: str) -> bool:
        tokens = alias_tokens(name)
        if not tokens or len(tokens) > 6:
            return False

        if any(token in non_person_tokens for token in tokens):
            return False

        # A short surname like Mann/Saha may still be a valid alias if a
        # longer candidate in the same evidence contains that exact token.
        if len(tokens) == 1:
            token = tokens[0]
            if len(token) < 5 and not any(
                token in candidate_tokens
                for candidate_tokens in longer_name_sets
            ):
                return False

        return True

    names = [
        name
        for name in all_names
        if plausible_person_candidate(name)
    ]
    if not names:
        return None

    def token_set(value: str) -> set[str]:
        return set(alias_tokens(value))

    def specificity(value: str) -> tuple[int, int]:
        tokens = token_set(value)
        return (len(tokens), len(value))

    # Consolidate shortened aliases under the most specific compatible name:
    # Mann -> Bhagwant Mann, Saha -> Manik Saha, Dhami -> Pushkar Singh Dhami.
    canonical_for: dict[str, str] = {}
    for name in names:
        source_tokens = token_set(name)
        compatible = [
            candidate
            for candidate in names
            if source_tokens and source_tokens.issubset(token_set(candidate))
        ]
        canonical = max(compatible, key=specificity) if compatible else name
        canonical_for[_normalise(name)] = canonical

    groups: dict[str, dict[str, Any]] = {}
    for name in names:
        canonical = canonical_for[_normalise(name)]
        key = _normalise(canonical)
        group = groups.setdefault(
            key,
            {
                "name": canonical,
                "aliases": [],
            },
        )
        if name not in group["aliases"]:
            group["aliases"].append(name)

    scored: list[tuple[float, float, StateCmFact]] = []

    for group in groups.values():
        canonical_name = str(group["name"])
        aliases = list(group["aliases"])

        positive: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        # Union evidence supporting any alias of the same person.
        for alias in aliases:
            for item in _positive_evidence(alias, evidence):
                url = str(item.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                positive.append(item)
                seen_urls.add(url)

        if not _evidence_quality_ok(positive):
            continue

        official = [
            item
            for item in positive
            if str(item.get("source_type") or "") == "official"
        ]
        trusted = [
            item
            for item in positive
            if str(item.get("source_type") or "")
            in {
                "reputable_news",
                "trusted_reference",
                "primary_platform",
            }
        ]
        trusted_urls = {
            str(item.get("url") or "")
            for item in trusted
            if str(item.get("url") or "").strip()
        }
        independent = len(
            {
                str(item.get("url") or "")
                for item in positive
                if str(item.get("url") or "").strip()
            }
        )
        newest = max(
            (_source_date_score(item) for item in positive),
            default=0.0,
        )

        specificity_bonus = min(len(alias_tokens(canonical_name)), 4)

        if official:
            confidence = 0.97 if len(official) >= 2 else 0.95
            quality_score = (
                100.0
                + 10.0 * len(official)
                + 5.0 * len(trusted)
                + independent
                + specificity_bonus
            )
        elif len(trusted_urls) >= 2:
            confidence = 0.91
            quality_score = (
                60.0
                + 6.0 * len(trusted)
                + independent
                + specificity_bonus
            )
        else:
            continue

        if confidence < min_confidence:
            continue

        urls = list(
            dict.fromkeys(
                str(item.get("url") or "").strip()
                for item in positive
                if str(item.get("url") or "").strip()
            )
        )[:3]
        if not urls:
            continue

        scored.append(
            (
                quality_score,
                newest,
                StateCmFact(
                    state=state,
                    chief_minister=canonical_name,
                    confidence=confidence,
                    evidence_urls=urls,
                    evidence=positive,
                ),
            )
        )

    if not scored:
        return None

    scored.sort(
        key=lambda row: (
            row[0],
            row[1],
            len(row[2].chief_minister),
        ),
        reverse=True,
    )
    top_score, top_date, top = scored[0]

    # Preserve fail-closed behavior for genuinely competing people.
    if len(scored) > 1:
        second_score, second_date, second = scored[1]
        if _normalise(second.chief_minister) != _normalise(
            top.chief_minister
        ):
            close_quality = second_score >= (top_score - 8.0)
            close_date = (
                top_date == 0.0
                or second_date == 0.0
                or abs(top_date - second_date) < 21 * 24 * 3600
            )
            if close_quality and close_date:
                return None

    return top




def _merge_ranked_sources(
    old: list[dict[str, Any]],
    new: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return _dedupe_and_rank([*old, *new], 10)
# VASUKI_V49_1_1_DETERMINISTIC_CM_ADJUDICATION_END


def _source_block(state: str, evidence: list[dict[str, Any]]) -> str:
    parts = [f"STATE: {state}"]
    for index, item in enumerate(evidence, 1):
        parts.append(
            f"SOURCE {index}\n"
            f"TYPE: {item.get('source_type') or 'other'}\n"
            f"TITLE: {item.get('title') or 'Source'}\n"
            f"URL: {item.get('url') or ''}\n"
            f"DATE: {item.get('published_date') or 'not provided'}\n"
            f"CONTENT: {str(item.get('content') or '')[:1800]}"
        )
    return "\n".join(parts)


def _parse_json_results(raw: str) -> list[dict[str, Any]]:
    text = str(raw or "").strip()
    if not text:
        return []
    candidates: list[str] = [text]
    candidates.extend(re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.I | re.S))
    array_match = re.search(r"\[\s*\{.*\}\s*\]", text, flags=re.S)
    if array_match:
        candidates.append(array_match.group(0))
    object_match = re.search(r"\{.*\}", text, flags=re.S)
    if object_match:
        candidates.append(object_match.group(0))
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("results", "states", "items"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
    return []


async def _adjudicate_batch(
    settings: Any,
    states: list[str],
    grouped: dict[str, list[dict[str, Any]]],
    *,
    as_of: str,
) -> tuple[list[dict[str, Any]], str]:
    import app.main as legacy

    pack = "\n\n".join(_source_block(state, grouped.get(state, [])) for state in states)
    expected = json.dumps(states, ensure_ascii=False)
    prompt = f"""
You are a strict current-officeholder verifier.

AS OF: {as_of}
STATES TO VERIFY: {expected}

Use ONLY the evidence pack below. Do not use model memory.

Hard rules:
- "Deputy Chief Minister", "Leader of Opposition", "former CM", candidates,
  party presidents and cabinet ministers are NOT the Chief Minister.
- Prefer an explicit current official government source.
- If official evidence conflicts with news, use the newer official evidence.
- If there is no source that actually supports the person's CURRENT CM role,
  mark the state insufficient.
- Return the person's name in English/Latin script where the evidence permits.
- Never guess a missing name.
- Return ONLY JSON in this exact structure:
{{
  "results": [
    {{
      "state": "exact requested state",
      "chief_minister": "name or empty string",
      "confidence": 0.0,
      "status": "verified or insufficient",
      "evidence_urls": ["supporting URL"]
    }}
  ]
}}

EVIDENCE PACK:
{pack}
""".strip()

    try:
        raw, provider = await legacy.route_chat(
            "auto",
            [{"role": "user", "content": prompt}],
            settings,
            pack,
            require_current=False,
            as_of=as_of,
        )
    except Exception as exc:
        return [], f"chat-verifier-unavailable:{type(exc).__name__}"
    return _parse_json_results(raw), str(provider or "auto")


def _validate_candidate(
    state: str,
    result: dict[str, Any] | None,
    evidence: list[dict[str, Any]],
    *,
    min_confidence: float,
) -> StateCmFact | None:
    if not result:
        return None
    if str(result.get("state") or "").strip().casefold() != state.casefold():
        return None
    if str(result.get("status") or "").strip().casefold() != "verified":
        return None

    name = re.sub(r"\s+", " ", str(result.get("chief_minister") or "")).strip()
    if len(name) < 3 or len(name) > 120:
        return None
    try:
        confidence = float(result.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < min_confidence:
        return None

    positive = _positive_evidence(name, evidence)
    if not _evidence_quality_ok(positive):
        return None

    allowed = {str(item.get("url") or "").strip() for item in positive}
    cited = [
        str(url).strip() for url in (result.get("evidence_urls") or [])
        if str(url).strip() in allowed
    ]
    chosen = cited or [str(item.get("url") or "").strip() for item in positive]
    chosen = list(dict.fromkeys(url for url in chosen if url))[:3]
    if not chosen:
        return None

    return StateCmFact(
        state=state,
        chief_minister=name,
        confidence=confidence,
        evidence_urls=chosen,
        evidence=positive,
    )


async def _deep_retry_state(
    settings: Any,
    state: str,
    *,
    as_of: str,
) -> list[dict[str, Any]]:
    queries = (
        (
            f"As of {as_of}, who is the CURRENT serving Chief Minister of {state}, India? "
            "Find an explicit official government/CMO/profile/oath source naming the current CM. "
            "Exclude deputy, former, opposition and candidate roles."
        ),
        (
            f'"Chief Minister" "{state}" current serving official government {as_of}'
        ),
        (
            f'{state} current Chief Minister official profile oath appointment {as_of}'
        ),
    )

    jobs = []
    for query in queries:
        jobs.append(
            tavily_search(
                query,
                settings,
                max_results=8,
                topic="general",
                search_depth="advanced",
                entity=state,
                content_limit=2600,
            )
        )

    # One official-domain pass is enough; general queries above already cover
    # wider sources.
    jobs.append(
        tavily_search(
            queries[0],
            settings,
            max_results=8,
            topic="general",
            include_domains=("gov.in", "nic.in"),
            search_depth="advanced",
            entity=state,
            content_limit=2600,
        )
    )

    if str(getattr(settings, "exa_api", "") or "").strip():
        jobs.append(
            exa_search(
                queries[0],
                settings,
                max_results=8,
                entity=state,
                content_limit=2600,
            )
        )

    collected: list[dict[str, Any]] = []
    done = await asyncio.gather(*jobs, return_exceptions=True)
    for result in done:
        if not isinstance(result, Exception):
            collected.extend(result)

    return _dedupe_and_rank(collected, 16)



def _group_sources(sources: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = {state: [] for state in INDIA_STATES}
    lookup = {state.casefold(): state for state in INDIA_STATES}
    for item in sources:
        entity = str(item.get("entity") or "").strip().casefold()
        state = lookup.get(entity)
        if state:
            grouped[state].append(item)
    return grouped


async def build_verified_india_cm_snapshot(settings: Any, *, as_of: str) -> VerifiedCmSnapshot:
    sources, search_provider = await search_all_india_state_cms(settings, as_of)
    grouped = _group_sources(sources)

    missing_evidence = [state for state in INDIA_STATES if not grouped.get(state)]
    if missing_evidence:
        retry_sem = asyncio.Semaphore(4)
        async def fill(state: str):
            async with retry_sem:
                return state, await _deep_retry_state(settings, state, as_of=as_of)
        for state, items in await asyncio.gather(*(fill(s) for s in missing_evidence)):
            if items:
                grouped[state] = items

    still_missing = [state for state in INDIA_STATES if not grouped.get(state)]
    if still_missing:
        raise RuntimeError(
            "Authoritative CM verification has no evidence for: " + ", ".join(still_missing)
        )

    min_confidence = max(
        0.75,
        min(0.99, float(getattr(settings, "v49_1_cm_min_confidence", 0.84))),
    )
    providers: list[str] = ["deterministic-source-adjudicator-v49.1.1"]
    facts: dict[str, StateCmFact] = {}

    # Phase 1: source-only adjudication. This consumes no chat-provider quota.
    for state in INDIA_STATES:
        fact = _deterministic_fact(
            state,
            grouped[state],
            min_confidence=min_confidence,
        )
        if fact:
            facts[state] = fact

    # Phase 2: deeper live retrieval only for unresolved states.
    unresolved = [state for state in INDIA_STATES if state not in facts]
    if unresolved:
        retry_sem = asyncio.Semaphore(4)

        async def deepen(state: str):
            async with retry_sem:
                deeper = await _deep_retry_state(settings, state, as_of=as_of)
                return state, deeper

        deepened = await asyncio.gather(*(deepen(state) for state in unresolved))
        for state, deeper in deepened:
            if deeper:
                grouped[state] = _merge_ranked_sources(grouped[state], deeper)
            fact = _deterministic_fact(
                state,
                grouped[state],
                min_confidence=min_confidence,
            )
            if fact:
                facts[state] = fact

    # Phase 3: LLM is a LAST resort and runs sequentially. Provider quota,
    # cooldown, 402/404/429 errors are caught by _adjudicate_batch.
    unresolved = [state for state in INDIA_STATES if state not in facts]
    if unresolved and bool(getattr(settings, "v49_1_llm_fallback_enabled", True)):
        for state in list(unresolved):
            items, provider = await _adjudicate_batch(
                settings,
                [state],
                grouped,
                as_of=as_of,
            )
            providers.append(provider)
            result = next(
                (
                    item
                    for item in items
                    if str(item.get("state") or "").strip() == state
                ),
                None,
            )
            fact = _validate_candidate(
                state,
                result,
                grouped[state],
                min_confidence=min_confidence,
            )
            if fact:
                facts[state] = fact

    unresolved = [state for state in INDIA_STATES if state not in facts]
    if unresolved:
        raise RuntimeError(
            "Authoritative CM verification refused to guess for: " + ", ".join(unresolved)
        )

    ordered = [facts[state] for state in INDIA_STATES]
    min_verified_confidence = min(item.confidence for item in ordered)
    lines = [f"भारत के 28 राज्यों के वर्तमान मुख्यमंत्री — सत्यापित: {as_of}", ""]
    all_sources: list[dict[str, Any]] = []
    all_urls: list[str] = []
    for index, fact in enumerate(ordered, 1):
        url = fact.evidence_urls[0]
        lines.append(f"{index}. {fact.state}: {fact.chief_minister} — Source: {url}")
        all_urls.extend(fact.evidence_urls)
        for item in fact.evidence:
            copied = dict(item)
            copied["entity"] = fact.state
            all_sources.append(copied)

    display_answer = "\n".join(lines)
    marker = (
        f"<!--{CM_SNAPSHOT_MARKER}|as_of={_now_iso()}|"
        f"confidence={min_verified_confidence:.3f}-->"
    )
    stored_answer = marker + "\n" + display_answer

    return VerifiedCmSnapshot(
        stored_answer=stored_answer,
        display_answer=display_answer,
        sources=_dedupe_and_rank(all_sources, 56),
        evidence_urls=list(dict.fromkeys(url for url in all_urls if url))[:56],
        search_provider=str(search_provider),
        verifier_provider=",".join(dict.fromkeys(p for p in providers if p)) or "auto",
        confidence=min_verified_confidence,
        verified_entities=len(ordered),
    )


_MARKER_RE = re.compile(
    rf"<!--{CM_SNAPSHOT_MARKER}\|as_of=([^|]+)\|confidence=([0-9.]+)-->\s*",
    re.I,
)


def extract_recent_cm_snapshot(hits: list[Any], *, max_age_hours: float) -> str | None:
    now = datetime.now(timezone.utc)
    max_age = timedelta(hours=max(0.25, float(max_age_hours)))
    for hit in hits:
        answer = str(getattr(hit, "answer", "") or "")
        match = _MARKER_RE.match(answer)
        if not match:
            continue
        try:
            timestamp = datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        age = now - timestamp.astimezone(timezone.utc)
        if age < timedelta(0) or age > max_age:
            continue
        display = _MARKER_RE.sub("", answer, count=1).strip()
        if display:
            return display
    return None
