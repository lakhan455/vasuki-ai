from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class EvidencePack:
    sources: tuple[dict[str, Any], ...]
    confidence: float
    disagreement: bool
    source_count: int
    domain_count: int
    context: str


def _domain(item: dict[str, Any]) -> str:
    value = str(item.get("domain") or "").strip().casefold()
    if value:
        return value.removeprefix("www.")
    url = str(item.get("url") or "").strip()
    try:
        host = urlparse(url).hostname
        return host.casefold().removeprefix("www.") if host else ""
    except Exception:
        return ""


def _authority(item: dict[str, Any]) -> float:
    source_type = str(item.get("source_type") or "").casefold()
    domain = _domain(item)
    if source_type in {"official", "government", "primary", "regulator"}:
        return 1.0
    if domain.endswith((".gov", ".gov.in", ".nic.in", ".mil")):
        return 0.98
    if source_type in {"research", "documentation", "docs", "academic"}:
        return 0.88
    if source_type in {"news", "press"}:
        return 0.76
    return 0.58


def _published_age_days(value: Any) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.fromisoformat(raw[:10])
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    return max(0.0, delta.total_seconds() / 86400.0)


def _freshness(item: dict[str, Any], current_required: bool) -> float:
    age = _published_age_days(item.get("published_date"))
    if age is None:
        return 0.48 if current_required else 0.62
    if age <= 2:
        return 1.0
    if age <= 14:
        return 0.92
    if age <= 45:
        return 0.82
    if age <= 365:
        return 0.68
    return 0.42 if current_required else 0.58


def _score(item: dict[str, Any], current_required: bool) -> float:
    content = str(item.get("content") or "")
    completeness = min(1.0, len(content) / 1200.0)
    value = (
        _authority(item) * 0.58
        + _freshness(item, current_required) * 0.30
        + completeness * 0.12
    )
    return round(max(0.0, min(1.0, value)), 4)


def _dedupe(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in sources:
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip().casefold()
        domain = _domain(item)
        key = url or f"{domain}|{title}"
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(dict(item))
    return result


_PERCENT = re.compile(r"\b\d+(?:\.\d+)?\s*%")
_VERSION = re.compile(r"\bv?\d+(?:\.\d+){1,3}\b", re.I)
_MONEY = re.compile(r"(?:₹|\$|€|£)\s*\d+(?:[\d,]*)(?:\.\d+)?")
_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")


def _single_value_disagreement(
    query: str,
    sources: list[dict[str, Any]],
) -> bool:
    if len(sources) < 2:
        return False

    q = str(query or "").casefold()
    patterns: list[re.Pattern[str]] = []

    if any(
        token in q
        for token in ("percent", "percentage", "rate", "repo rate", "interest")
    ):
        patterns.append(_PERCENT)
    if "version" in q or "release" in q:
        patterns.append(_VERSION)
    if any(token in q for token in ("price", "cost", "how much", "amount")):
        patterns.append(_MONEY)

    if not patterns and not any(
        token in q
        for token in ("what is the number", "how many", "when", "date")
    ):
        return False

    if not patterns:
        patterns.append(_NUMBER)

    candidate_sets: list[set[str]] = []
    for item in sources[:3]:
        text = (
            str(item.get("title") or "")
            + " "
            + str(item.get("content") or "")[:900]
        )
        values: set[str] = set()
        for pattern in patterns:
            values.update(
                match.group(0).replace(" ", "")
                for match in pattern.finditer(text)
            )
        if values:
            candidate_sets.append(values)

    if len(candidate_sets) < 2:
        return False

    first = candidate_sets[0]
    second = candidate_sets[1]
    return bool(first and second and first.isdisjoint(second))


def assess_and_rank_sources(
    query: str,
    sources: list[dict[str, Any]],
    *,
    current_required: bool,
    limit: int = 10,
) -> EvidencePack:
    ranked = _dedupe(sources)

    for item in ranked:
        item["_vasuki_evidence_score"] = _score(
            item,
            current_required,
        )

    ranked.sort(
        key=lambda row: (
            -float(row.get("_vasuki_evidence_score") or 0),
            str(row.get("published_date") or ""),
        )
    )
    ranked = ranked[: max(1, min(int(limit), 12))]

    domains = {
        _domain(item)
        for item in ranked
        if _domain(item)
    }

    avg = (
        sum(
            float(item.get("_vasuki_evidence_score") or 0)
            for item in ranked
        )
        / len(ranked)
        if ranked
        else 0.0
    )

    diversity = min(1.0, len(domains) / 3.0)
    confidence = round(
        max(0.0, min(1.0, avg * 0.78 + diversity * 0.22)),
        3,
    )
    disagreement = _single_value_disagreement(
        query,
        ranked,
    )

    lines = [
        "VASUKI V54 KNOWLEDGE / EVIDENCE POLICY:",
        (
            f"Ranked sources={len(ranked)}; independent domains={len(domains)}; "
            f"evidence confidence={confidence:.3f}."
        ),
        (
            "Prefer official/primary and newer evidence over weaker secondary summaries."
        ),
        (
            "Never treat source order alone as proof; compare the actual claim "
            "and publication/update date."
        ),
    ]

    if disagreement:
        lines.append(
            (
                "Potential source disagreement detected for a single-value fact. "
                "Explicitly compare the conflicting values and do not silently choose one."
            )
        )

    for index, item in enumerate(ranked[:6], 1):
        lines.append(
            (
                f"[EVIDENCE RANK {index}] domain={_domain(item) or 'unknown'} "
                f"score={float(item.get('_vasuki_evidence_score') or 0):.2f} "
                f"date={item.get('published_date') or 'unknown'} "
                f"title={str(item.get('title') or 'Source')[:180]}"
            )
        )

    return EvidencePack(
        sources=tuple(ranked),
        confidence=confidence,
        disagreement=disagreement,
        source_count=len(ranked),
        domain_count=len(domains),
        context="\n".join(lines),
    )


def health_snapshot() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v54",
        "name": "Vasuki Knowledge Brain",
        "features": [
            "source-authority-ranking",
            "freshness-scoring",
            "domain-diversity-scoring",
            "conservative-disagreement-detection",
            "evidence-confidence",
            "no-silent-conflict-resolution",
        ],
        "mutates_external_sources": False,
        "new_database_migration_required": False,
        "new_api_key_required": False,
    }
