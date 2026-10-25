from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse


_HIGH_STAKES_CURRENT = re.compile(
    r"\b(?:founder|co[- ]?founder|ceo|chief executive|chairman|president|"
    r"prime minister|chief minister|governor|minister|mayor|office holder|"
    r"current head|who runs|who is the current|ka founder|ka ceo|kon (?:hai|he)|"
    r"mukhyamantri|pradhanmantri|rashtrapati|rajyapal|mantri)\b",
    re.I,
)

_CURRENT_SIGNAL = re.compile(
    r"\b(?:current|currently|latest|today|now|recent|live|present|updated|"
    r"newest|as of|abhi|abi|filhal|haal mein|aaj|vartaman|202[4-9])\b|"
    r"(?:अभी|वर्तमान|आज|नवीनतम|लेटेस्ट|ताज़ा|ताजा)",
    re.I,
)

_SENSITIVE_SIGNAL = re.compile(
    r"\b(?:law|rule|regulation|policy|medical|medicine|treatment|drug|"
    r"stock|share price|interest rate|tax|recall|outage|security advisory)\b",
    re.I,
)

_TRUSTED_TYPES = {
    "official",
    "primary_platform",
    "reputable_news",
    "trusted_reference",
}
_AUTHORITATIVE_TYPES = {"official", "primary_platform"}


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    query: str
    current_sensitive: bool
    high_stakes: bool
    source_count: int
    independent_domains: int
    authoritative_sources: int
    trusted_sources: int
    dated_sources: int
    confidence: float
    safe_to_answer: bool
    safe_to_store: bool
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["issues"] = list(self.issues)
        return data


def _host(url: str) -> str:
    try:
        return (urlparse(str(url or "")).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def _source_type(item: dict[str, Any]) -> str:
    value = str(item.get("source_type") or item.get("type") or "").strip().lower()
    if value:
        return value
    host = _host(str(item.get("url") or ""))
    if host.endswith(".gov.in") or host.endswith(".nic.in") or host.endswith(".gov"):
        return "official"
    return "other"


def _usable(item: dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    url = str(item.get("url") or "").strip()
    content = str(
        item.get("content")
        or item.get("snippet")
        or item.get("text")
        or item.get("title")
        or ""
    ).strip()
    return bool(url and content)


def is_current_sensitive(query: str) -> bool:
    text = str(query or "")
    return bool(
        _CURRENT_SIGNAL.search(text)
        or _HIGH_STAKES_CURRENT.search(text)
        or _SENSITIVE_SIGNAL.search(text)
    )


def is_high_stakes_current_fact(query: str) -> bool:
    text = str(query or "")
    return bool(_HIGH_STAKES_CURRENT.search(text) or _SENSITIVE_SIGNAL.search(text))


def assess_current_evidence(
    query: str,
    sources: list[dict[str, Any]] | None,
    *,
    require_current: bool = True,
    min_sources: int = 2,
    min_domains: int = 2,
) -> EvidenceAssessment:
    rows = [item for item in (sources or []) if _usable(item)]
    current_sensitive = bool(require_current or is_current_sensitive(query))
    high_stakes = bool(current_sensitive and is_high_stakes_current_fact(query))

    domains = {_host(str(item.get("url") or "")) for item in rows}
    domains.discard("")

    source_types = [_source_type(item) for item in rows]
    authoritative = sum(1 for value in source_types if value in _AUTHORITATIVE_TYPES)
    trusted = sum(1 for value in source_types if value in _TRUSTED_TYPES)
    dated = sum(1 for item in rows if str(item.get("published_date") or "").strip())

    trusted_domains = {
        _host(str(item.get("url") or ""))
        for item in rows
        if _source_type(item) in _TRUSTED_TYPES
    }
    trusted_domains.discard("")

    issues: list[str] = []
    source_floor = max(1, int(min_sources))
    domain_floor = max(1, int(min_domains))

    if current_sensitive and len(rows) < 1:
        issues.append("no usable live evidence")
    if high_stakes and authoritative == 0 and len(trusted_domains) < domain_floor:
        issues.append(
            "high-stakes current fact lacks authoritative or independent trusted corroboration"
        )
    if current_sensitive and len(domains) < 1:
        issues.append("no independent source domain")
    if len(rows) < source_floor:
        issues.append(f"fewer than {source_floor} usable sources")
    if len(domains) < domain_floor:
        issues.append(f"fewer than {domain_floor} independent domains")

    if not current_sensitive:
        safe_to_answer = True
    elif high_stakes:
        safe_to_answer = authoritative >= 1 or len(trusted_domains) >= domain_floor
    else:
        safe_to_answer = bool(
            rows
            and (
                authoritative >= 1
                or trusted >= 1
                or len(domains) >= domain_floor
            )
        )

    safe_to_store = bool(
        current_sensitive
        and len(rows) >= source_floor
        and len(domains) >= domain_floor
        and (authoritative >= 1 or len(trusted_domains) >= domain_floor)
    )

    confidence = 0.52
    confidence += min(0.22, authoritative * 0.11)
    confidence += min(0.12, len(trusted_domains) * 0.04)
    confidence += min(0.06, max(0, len(domains) - 1) * 0.02)
    confidence += min(0.04, dated * 0.01)
    if safe_to_answer:
        confidence = max(confidence, 0.78 if high_stakes else 0.74)
    if safe_to_store:
        confidence = max(confidence, 0.84)
    confidence = round(max(0.0, min(0.96, confidence)), 3)

    return EvidenceAssessment(
        query=str(query or "")[:700],
        current_sensitive=current_sensitive,
        high_stakes=high_stakes,
        source_count=len(rows),
        independent_domains=len(domains),
        authoritative_sources=authoritative,
        trusted_sources=trusted,
        dated_sources=dated,
        confidence=confidence,
        safe_to_answer=safe_to_answer,
        safe_to_store=safe_to_store,
        issues=tuple(dict.fromkeys(issues)),
    )


def should_fail_closed(assessment: EvidenceAssessment) -> bool:
    return bool(
        assessment.current_sensitive
        and assessment.high_stakes
        and not assessment.safe_to_answer
    )


def truth_guard_message(assessment: EvidenceAssessment) -> str:
    if assessment.source_count == 0:
        return (
            "I could not safely verify this current fact because live evidence "
            "is unavailable right now. Please retry shortly."
        )
    return (
        "I found some live information, but not enough authoritative or "
        "independent evidence to verify this current fact safely. "
        "I will not guess; please retry shortly."
    )


def evidence_policy_context(assessment: EvidenceAssessment) -> str:
    issues = "; ".join(assessment.issues) if assessment.issues else "none"
    return (
        "V50 EVIDENCE POLICY:\n"
        f"current_sensitive={assessment.current_sensitive}\n"
        f"high_stakes={assessment.high_stakes}\n"
        f"source_count={assessment.source_count}\n"
        f"independent_domains={assessment.independent_domains}\n"
        f"authoritative_sources={assessment.authoritative_sources}\n"
        f"trusted_sources={assessment.trusted_sources}\n"
        f"confidence={assessment.confidence:.3f}\n"
        f"safe_to_answer={assessment.safe_to_answer}\n"
        f"issues={issues}\n"
        "For current factual claims use only the supplied evidence. "
        "Do not fill missing current facts from model memory. "
        "If a requested current detail is unsupported, explicitly mark it unverified."
    )


def extract_sources_from_context(context: str) -> list[dict[str, Any]]:
    text = str(context or "")
    if not text.strip():
        return []

    blocks = re.split(r"\n{2,}(?=\[\d+\]\s)", text)
    results: list[dict[str, Any]] = []
    for block in blocks:
        if not re.match(r"^\[\d+\]\s", block.strip()):
            continue

        def field(*names: str) -> str:
            for name in names:
                match = re.search(rf"(?mi)^{re.escape(name)}:\s*(.*)$", block)
                if match:
                    return match.group(1).strip()
            return ""

        content_match = re.search(r"(?mis)^CONTENT:\s*\n?(.*)$", block)
        item = {
            "entity": field("ENTITY"),
            "source_type": field("SOURCE TYPE", "TYPE"),
            "title": field("TITLE"),
            "url": field("URL"),
            "published_date": field("PUBLISHED/UPDATED", "DATE"),
            "content": content_match.group(1).strip() if content_match else "",
        }
        if item["url"] or item["content"]:
            results.append(item)
    return results
