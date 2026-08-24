from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class VerificationResult:
    score: float
    hallucination_risk: float
    needs_retry: bool
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["issues"] = list(self.issues)
        return data


def verify_answer(
    prompt: str,
    answer: str,
    *,
    sources: list[dict[str, Any]] | None = None,
    current_required: bool = False,
) -> VerificationResult:
    p = str(prompt or "").strip()
    a = str(answer or "").strip()
    sources = sources or []
    score = 100.0
    risk = 10.0
    issues: list[str] = []

    if not a:
        return VerificationResult(0.0, 100.0, True, ("empty answer",))
    if len(p) > 800 and len(a) < 180:
        score -= 18
        issues.append("answer may be incomplete for a large request")
    if current_required and not sources:
        score -= 28
        risk += 28
        issues.append("current-information answer has no supporting sources")
    if re.search(r"\b(?:TODO|TBD|placeholder|lorem ipsum)\b", a, re.I):
        score -= 22
        risk += 12
        issues.append("placeholder/incomplete content detected")
    if re.search(r"\b(?:latest|today|current|currently|right now)\b", p, re.I):
        if not re.search(r"\b20\d{2}\b|https?://|\bsource\b|\bcitation\b", a, re.I):
            score -= 10
            risk += 12
            issues.append("freshness-sensitive answer lacks visible date/source signal")
    if re.search(r"\b(?:all|every|complete|full list|sabhi|saare)\b", p, re.I) and len(a) < 250:
        score -= 12
        issues.append("completeness request may be under-answered")
    if re.search(r"\b(?:calculate|solve|equation|percentage|total)\b", p, re.I) and not re.search(r"\d", a):
        score -= 18
        issues.append("calculation request has no numeric result")

    unsupported_specificity = len(re.findall(r"\b(?:19|20)\d{2}\b|\b\d+(?:\.\d+)?%\b|\$\d+", a))
    if unsupported_specificity and not sources and current_required:
        penalty = min(18, unsupported_specificity * 3)
        score -= penalty
        risk += penalty

    score = round(max(0.0, min(100.0, score)), 2)
    risk = round(max(0.0, min(100.0, risk)), 2)
    return VerificationResult(score, risk, score < 68.0 or risk >= 60.0, tuple(issues))
