from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import Settings
from app.services.research import needs_live_web, search_web


_CORRECTION_MARKERS = (
    "nahi", "nhi", "nahin", "galat", "wrong", "actually", "असल में",
    "नहीं", "गलत", "सही जवाब", "sahi jawab", "correct answer",
    "the correct answer", "instead", "बल्कि",
)

_PRIVATE_PATTERNS = (
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"(?<!\d)(?:\+?91[-\s]?)?[6-9]\d{9}(?!\d)"),
    re.compile(r"\b(?:password|passwd|api[_ -]?key|secret|access[_ -]?token|otp|aadhaar|pan card)\b", re.I),
)

_FACT_WORDS = re.compile(
    r"\b(who|what|which|when|where|how many|highest|largest|most|"
    r"kaun|kon|kiske|kisne|kya|kab|kahan|kitne|sabse|jada|zyada|"
    r"कौन|किसके|किसने|क्या|कब|कहाँ|कितने|सबसे)\b",
    re.I,
)
_COMPLEX_WORDS = re.compile(
    r"\b(code|website|app|essay|story|poem|design|image|prompt|"
    r"explain in detail|full project|complete file)\b",
    re.I,
)


@dataclass(slots=True)
class KnowledgeHit:
    id: str
    canonical_question: str
    answer: str
    aliases: list[str]
    evidence_urls: list[str]
    dynamic: bool
    valid_until: str | None
    score: float
    confidence: float


def _headers(settings: Settings) -> dict[str, str]:
    key = (
        settings.supabase_secret_key
        or settings.supabase_service_role_key
        or ""
    )
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
    }
    # New sb_secret_* keys use the apikey header. Legacy service_role JWT keys
    # also need the Bearer header.
    if key and not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _base_url(settings: Settings) -> str:
    return (settings.supabase_url or "").rstrip("/")


def _normalise(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[^\w\u0900-\u097f]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _subject_key(question: str) -> str:
    normalised = _normalise(question)
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def _contains_private_data(text: str) -> bool:
    return any(pattern.search(text) for pattern in _PRIVATE_PATTERNS)


def is_direct_fact_question(query: str) -> bool:
    cleaned = query.strip()
    if not cleaned or len(cleaned) > 240:
        return False
    if _COMPLEX_WORDS.search(cleaned):
        return False
    return bool(_FACT_WORDS.search(cleaned) or cleaned.endswith("?"))


def extract_correction(messages: list[dict[str, str]]) -> tuple[str, str] | None:
    if len(messages) < 3:
        return None

    last_user_index = next(
        (
            index
            for index in range(len(messages) - 1, -1, -1)
            if messages[index].get("role") == "user"
        ),
        None,
    )
    if last_user_index is None:
        return None

    correction_text = str(messages[last_user_index].get("content") or "").strip()
    if not correction_text or len(correction_text) > 700:
        return None

    lower = correction_text.casefold()
    marker_positions: list[tuple[int, int]] = []
    for marker in _CORRECTION_MARKERS:
        for match in re.finditer(re.escape(marker.casefold()), lower):
            marker_positions.append((match.start(), match.end()))

    if not marker_positions:
        return None

    assistant_index = next(
        (
            index
            for index in range(last_user_index - 1, -1, -1)
            if messages[index].get("role") == "assistant"
        ),
        None,
    )
    if assistant_index is None:
        return None

    question_index = next(
        (
            index
            for index in range(assistant_index - 1, -1, -1)
            if messages[index].get("role") == "user"
        ),
        None,
    )
    if question_index is None:
        return None

    question = str(messages[question_index].get("content") or "").strip()
    if not question or len(question) > 1000:
        return None

    _, marker_end = max(marker_positions, key=lambda item: item[0])
    candidate = correction_text[marker_end:].strip(" \t\r\n,:;-–—")
    candidate = re.sub(
        r"^(?:is|hai|he|h|है|तो|to)\s+",
        "",
        candidate,
        flags=re.I,
    )
    candidate = re.sub(
        r"\s+(?:hai|he|h|है)\s*[.!?]*$",
        "",
        candidate,
        flags=re.I,
    ).strip()

    if len(candidate) < 2 or len(candidate) > 500:
        return None
    if _contains_private_data(question) or _contains_private_data(candidate):
        return None

    return question, candidate


async def find_verified_knowledge(
    query: str,
    settings: Settings,
) -> list[KnowledgeHit]:
    if not settings.global_learning_configured:
        return []

    url = f"{_base_url(settings)}/rest/v1/rpc/match_global_knowledge"
    payload = {
        "search_text": query,
        "match_limit": settings.global_memory_max_results,
    }

    try:
        async with httpx.AsyncClient(
            timeout=min(6.0, float(settings.request_timeout_seconds))
        ) as client:
            response = await client.post(
                url,
                headers=_headers(settings),
                json=payload,
            )
            response.raise_for_status()
            rows = response.json()
    except Exception:
        return []

    hits: list[KnowledgeHit] = []
    for row in rows if isinstance(rows, list) else []:
        try:
            hits.append(
                KnowledgeHit(
                    id=str(row.get("id") or ""),
                    canonical_question=str(row.get("canonical_question") or ""),
                    answer=str(row.get("answer") or ""),
                    aliases=[
                        str(item)
                        for item in (row.get("aliases") or [])
                        if str(item).strip()
                    ],
                    evidence_urls=[
                        str(item)
                        for item in (row.get("evidence_urls") or [])
                        if str(item).strip()
                    ],
                    dynamic=bool(row.get("dynamic")),
                    valid_until=(
                        str(row.get("valid_until"))
                        if row.get("valid_until")
                        else None
                    ),
                    score=float(row.get("score") or 0.0),
                    confidence=float(row.get("confidence") or 0.0),
                )
            )
        except (TypeError, ValueError):
            continue

    return hits


def knowledge_context(hits: list[KnowledgeHit]) -> str:
    if not hits:
        return ""

    parts = [
        "VERIFIED SHARED VASUKI KNOWLEDGE:",
        "Use these facts when relevant. They were verified before being stored.",
    ]
    for index, hit in enumerate(hits, 1):
        parts.append(
            f"[MEMORY {index}]\n"
            f"QUESTION/TOPIC: {hit.canonical_question}\n"
            f"ANSWER: {hit.answer}\n"
            f"CONFIDENCE: {hit.confidence:.2f}\n"
            f"EVIDENCE URLS: {', '.join(hit.evidence_urls) or 'not stored'}"
        )
    return "\n\n".join(parts)


def hit_sources(hits: list[KnowledgeHit]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for hit in hits:
        if hit.evidence_urls:
            for url in hit.evidence_urls[:3]:
                sources.append(
                    {
                        "title": "Verified shared Vasuki knowledge",
                        "url": url,
                        "content": hit.answer,
                        "source_type": "shared_memory",
                        "entity": hit.canonical_question,
                    }
                )
        else:
            sources.append(
                {
                    "title": "Verified shared Vasuki knowledge",
                    "url": "",
                    "content": hit.answer,
                    "source_type": "shared_memory",
                    "entity": hit.canonical_question,
                }
            )
    return sources


def _evidence_context(sources: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for index, source in enumerate(sources, 1):
        parts.append(
            f"[{index}] TITLE: {source.get('title', 'Source')}\n"
            f"URL: {source.get('url', '')}\n"
            f"PUBLISHED/UPDATED: {source.get('published_date') or 'not provided'}\n"
            f"CONTENT:\n{source.get('content', '')}"
        )
    return "\n\n".join(parts)


def _parse_verdict(raw: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _clean_aliases(values: Any, question: str) -> list[str]:
    candidates = [question]
    if isinstance(values, list):
        candidates.extend(str(item) for item in values)

    result: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        cleaned = re.sub(r"\s+", " ", item).strip()
        key = cleaned.casefold()
        if not cleaned or len(cleaned) > 300 or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
        if len(result) >= 10:
            break
    return result


async def _save_feedback(
    question: str,
    proposed_answer: str,
    status: str,
    confidence: float,
    evidence_urls: list[str],
    settings: Settings,
) -> None:
    if not settings.global_learning_configured:
        return

    payload = {
        "question": question,
        "proposed_answer": proposed_answer,
        "status": status,
        "confidence": confidence,
        "evidence_urls": evidence_urls,
    }
    url = f"{_base_url(settings)}/rest/v1/knowledge_feedback"

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            await client.post(
                url,
                headers={
                    **_headers(settings),
                    "Prefer": "return=minimal",
                },
                json=payload,
            )
    except Exception:
        return


async def _upsert_verified(
    *,
    question: str,
    answer: str,
    aliases: list[str],
    evidence_urls: list[str],
    dynamic: bool,
    confidence: float,
    settings: Settings,
) -> None:
    now = datetime.now(timezone.utc)
    ttl_days = (
        settings.global_memory_dynamic_ttl_days
        if dynamic
        else settings.global_memory_stable_ttl_days
    )
    valid_until = now + timedelta(days=max(1, ttl_days))

    payload = {
        "p_subject_key": _subject_key(question),
        "p_canonical_question": question,
        "p_answer": answer,
        "p_aliases": aliases,
        "p_evidence_urls": evidence_urls,
        "p_dynamic": dynamic,
        "p_valid_until": valid_until.isoformat(),
        "p_confidence": confidence,
    }
    url = f"{_base_url(settings)}/rest/v1/rpc/upsert_global_knowledge"

    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.post(
            url,
            headers=_headers(settings),
            json=payload,
        )
        response.raise_for_status()


async def learn_from_correction(
    messages: list[dict[str, str]],
    settings: Settings,
    as_of: str,
) -> None:
    if not settings.global_learning_configured:
        return

    correction = extract_correction(messages)
    if not correction:
        return

    question, proposed_answer = correction
    dynamic = needs_live_web(question)

    try:
        sources, _provider = await search_web(
            f"{question}\nProposed correction to verify: {proposed_answer}",
            settings,
            max_results=6,
            require_current=dynamic,
            as_of=as_of,
        )
    except Exception:
        sources = []

    evidence_urls = [
        str(item.get("url") or "")
        for item in sources
        if str(item.get("url") or "").strip()
    ][:8]

    if not sources:
        await _save_feedback(
            question,
            proposed_answer,
            "pending",
            0.0,
            evidence_urls,
            settings,
        )
        return

    prompt = f"""
Verify a user-provided correction using ONLY the evidence pack.

Original question:
{question}

Proposed corrected answer:
{proposed_answer}

Current date:
{as_of}

Rules:
- Do not trust the user merely because they corrected the assistant.
- The evidence must clearly support the relationship between the question and answer.
- Reject claims that are contradicted, ambiguous, private, promotional, or unsupported.
- For current/changing facts, require current evidence.
- Create 3 to 8 concise question aliases in English, Hindi, or Hinglish so future phrasings can match.
- Return ONLY valid JSON in this exact shape:
{{"verified": true, "answer": "canonical concise answer", "confidence": 0.0, "aliases": ["..."]}}
or
{{"verified": false, "answer": "", "confidence": 0.0, "aliases": []}}
""".strip()

    verdict: dict[str, Any] | None = None
    try:
        from app.services.chat import route_chat

        raw_verdict, _provider = await route_chat(
            "auto",
            [{"role": "user", "content": prompt}],
            settings,
            _evidence_context(sources),
            require_current=False,
            as_of=as_of,
        )
        verdict = _parse_verdict(raw_verdict)
    except Exception:
        verdict = None

    verified = bool(verdict and verdict.get("verified") is True)
    try:
        confidence = float((verdict or {}).get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    if not verified or confidence < 0.72:
        await _save_feedback(
            question,
            proposed_answer,
            "rejected" if verdict else "pending",
            confidence,
            evidence_urls,
            settings,
        )
        return

    canonical_answer = str((verdict or {}).get("answer") or proposed_answer).strip()
    aliases = _clean_aliases((verdict or {}).get("aliases"), question)

    if (
        not canonical_answer
        or len(canonical_answer) > 1000
        or _contains_private_data(canonical_answer)
    ):
        await _save_feedback(
            question,
            proposed_answer,
            "rejected",
            confidence,
            evidence_urls,
            settings,
        )
        return

    try:
        await _upsert_verified(
            question=question,
            answer=canonical_answer,
            aliases=aliases,
            evidence_urls=evidence_urls,
            dynamic=dynamic,
            confidence=min(1.0, max(0.0, confidence)),
            settings=settings,
        )
        await _save_feedback(
            question,
            proposed_answer,
            "verified",
            confidence,
            evidence_urls,
            settings,
        )
    except Exception:
        await _save_feedback(
            question,
            proposed_answer,
            "pending",
            confidence,
            evidence_urls,
            settings,
        )
