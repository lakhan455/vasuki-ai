from __future__ import annotations

import re
from typing import Any


_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_NEGATION = re.compile(
    r"\b(no|not|never|none|false|cannot|can't|didn't|isn't|wasn't|"
    r"nahi|nhi|nahin)\b",
    re.I,
)
_NUMBER = re.compile(r"(?<!\w)(?:19|20)\d{2}|\b\d+(?:\.\d+)?%?\b")


def _tokens(text: str) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"\w+", text or "", flags=re.UNICODE)
        if len(token) > 2
    }


def _claims(answer: str) -> list[str]:
    claims: list[str] = []
    for raw in _SENTENCE.split(answer or ""):
        text = raw.strip(" -*#\t")
        if len(text) >= 20:
            claims.append(text[:1000])
    return claims[:60]


def _support_score(claim: str, source: str) -> float:
    claim_tokens = _tokens(claim)
    source_tokens = _tokens(source)

    if not claim_tokens or not source_tokens:
        return 0.0

    overlap = len(claim_tokens & source_tokens) / max(1, len(claim_tokens))

    claim_numbers = set(_NUMBER.findall(claim))
    source_numbers = set(_NUMBER.findall(source))

    if claim_numbers:
        number_score = len(claim_numbers & source_numbers) / len(claim_numbers)
        overlap = overlap * 0.75 + number_score * 0.25

    return max(0.0, min(1.0, overlap))


def verify_citations_v12(
    answer: str,
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_sources: list[dict[str, str]] = []

    for index, source in enumerate(sources or []):
        if not isinstance(source, dict):
            continue

        content = str(
            source.get("content")
            or source.get("text")
            or source.get("snippet")
            or ""
        ).strip()

        if not content:
            continue

        normalized_sources.append(
            {
                "id": str(source.get("id") or index + 1),
                "label": str(
                    source.get("url")
                    or source.get("title")
                    or f"source-{index + 1}"
                ),
                "content": content,
            }
        )

    results: list[dict[str, Any]] = []
    supported = 0
    contradicted = 0

    for claim in _claims(answer):
        best: dict[str, Any] | None = None

        for source in normalized_sources:
            score = _support_score(claim, source["content"])

            claim_neg = bool(_NEGATION.search(claim))
            source_neg = bool(_NEGATION.search(source["content"]))

            claim_numbers = set(_NUMBER.findall(claim))
            source_numbers = set(_NUMBER.findall(source["content"]))

            numeric_conflict = bool(
                claim_numbers
                and source_numbers
                and not claim_numbers.issubset(source_numbers)
                and score >= 0.22
            )

            negation_conflict = (
                claim_neg != source_neg
                and score >= 0.38
            )

            contradiction = numeric_conflict or negation_conflict

            candidate = {
                "source": source["label"],
                "source_id": source["id"],
                "score": round(score, 4),
                "contradiction": contradiction,
            }

            if best is None or candidate["score"] > best["score"]:
                best = candidate

        best_score = float(best["score"]) if best else 0.0
        contradiction = bool(best and best["contradiction"])

        if contradiction:
            status = "contradicted"
            contradicted += 1
        elif best_score >= 0.38:
            status = "supported"
            supported += 1
        else:
            status = "insufficient"

        results.append(
            {
                "claim": claim,
                "status": status,
                "support_score": round(best_score, 4),
                "source": best["source"] if best else None,
                "source_id": best["source_id"] if best else None,
            }
        )

    total = len(results)
    coverage = (
        100.0
        if total == 0
        else round(100.0 * supported / total, 2)
    )

    contradiction_pct = (
        0.0
        if total == 0
        else round(100.0 * contradicted / total, 2)
    )

    if contradicted:
        risk = "high"
    elif coverage >= 90:
        risk = "low"
    elif coverage >= 70:
        risk = "medium"
    else:
        risk = "high"

    return {
        "engine": "v12",
        "claim_count": total,
        "supported_count": supported,
        "contradicted_count": contradicted,
        "coverage_pct": coverage,
        "contradiction_pct": contradiction_pct,
        "risk": risk,
        "claims": results,
    }
