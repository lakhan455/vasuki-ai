from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from app.v13.verification import verify_answer


@dataclass(frozen=True, slots=True)
class CriticResult:
    score: float
    needs_repair: bool
    issues: tuple[str, ...]
    repair_instruction: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["issues"] = list(self.issues)
        return data


def _repetition_ratio(text: str) -> float:
    sentences = [
        re.sub(r"\s+", " ", item.strip().casefold())
        for item in re.split(r"(?<=[.!?])\s+|\n+", text)
        if len(item.strip()) >= 20
    ]
    if len(sentences) < 3:
        return 0.0
    return 1.0 - (len(set(sentences)) / len(sentences))


def critic_review(
    prompt: str,
    answer: str,
    *,
    sources: list[dict[str, Any]] | None = None,
    current_required: bool = False,
) -> CriticResult:
    base = verify_answer(
        prompt,
        answer,
        sources=sources or [],
        current_required=current_required,
    )
    score = float(base.score)
    issues = list(base.issues)
    p = str(prompt or "")
    a = str(answer or "")

    repetition = _repetition_ratio(a)
    if repetition >= 0.34:
        score -= 12
        issues.append("answer contains excessive repeated content")

    if re.search(r"\b(?:code|python|javascript|typescript|fastapi|react|sql)\b", p, re.I):
        if re.search(r"\b(?:write|create|fix|implement|code)\b", p, re.I) and "```" not in a:
            score -= 10
            issues.append("coding request may be missing an actionable code block")

    if re.search(r"\b(?:exact|strictly|only|must|do not|don't)\b", p, re.I) and len(a) < 40:
        score -= 8
        issues.append("strict constraints may not be fully addressed")

    score = round(max(0.0, min(100.0, score)), 2)
    needs_repair = bool(base.needs_retry or score < 72.0 or len(issues) >= 3)
    if needs_repair:
        bullet_text = "; ".join(issues[:6]) or "quality score below target"
        repair = (
            "Revise the answer without changing the user's intent. "
            f"Fix these issues: {bullet_text}. "
            "Preserve correct content, remove unsupported claims, and make the result complete."
        )
    else:
        repair = ""

    return CriticResult(score, needs_repair, tuple(issues), repair)
