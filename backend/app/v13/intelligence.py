from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

_CODE = (
    "bug", "debug", "traceback", "exception", "typeerror", "syntaxerror",
    "refactor", "python", "javascript", "typescript", "react", "next.js",
    "fastapi", "sql", "html", "css", "flutter", "kotlin", "gradle",
    "github", "powershell", "terminal", "api endpoint", "build failed",
)
_REASON = (
    "proof", "prove", "derive", "equation", "theorem", "algorithm", "logic",
    "reasoning", "puzzle", "calculate", "solve", "complexity", "why does",
)
_RESEARCH = (
    "research", "compare", "comparison", "analysis", "report", "verify",
    "sources", "citation", "evidence", "fact check", "deep research",
)
_CURRENT = (
    "latest", "current", "today", "right now", "currently", "recent",
    "news", "this week", "this month", "price today", "weather",
    "live score", "score today", "stock price", "exchange rate",
    "release date", "latest version", "who is the current",
)
_SIMPLE = (
    "hi", "hello", "hey", "thanks", "thank you", "good morning",
    "good evening", "define ", "meaning of ", "translate ",
)
_IMAGE = (
    "create an image", "generate an image", "make an image", "image of",
    "photo of", "poster", "logo", "illustration", "wallpaper",
)
_FILE = (
    "pdf", "docx", "word file", "excel", "xlsx", "spreadsheet", "zip",
    "file bana", "file create", "downloadable file", "presentation", "pptx",
)
_FOLLOWUP = re.compile(
    r"^(?:haan|ha|yes|ok|okay|karo|kar do|same|same wala|isko|ise|"
    r"ab kya|ab karo|fix karo|continue|aage|next|black me|red me|white me)"
    r"(?:\s+.*)?$",
    re.I,
)
_MATH = re.compile(r"(?:\d|\w)\s*[=<>+\-*/^]\s*(?:\d|\w)")
_YEAR = re.compile(r"\b20(?:2[4-9]|3\d)\b")


@dataclass(frozen=True, slots=True)
class IntelligencePlan:
    task_type: str
    difficulty: str
    tier: str
    language: str
    needs_web: bool
    needs_current: bool
    needs_verification: bool
    needs_calculator: bool
    needs_code_agent: bool
    needs_files: bool
    needs_image: bool
    is_followup: bool
    confidence: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data


def last_user_text(messages: list[dict[str, Any]]) -> str:
    return next(
        (
            str(item.get("content") or "")
            for item in reversed(messages)
            if item.get("role") == "user"
        ),
        "",
    )


def _previous_user_text(messages: list[dict[str, Any]]) -> str:
    seen = 0
    for item in reversed(messages):
        if item.get("role") != "user":
            continue
        seen += 1
        if seen == 2:
            return str(item.get("content") or "")
    return ""


def detect_language(text: str) -> str:
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    words = set(re.findall(r"[a-z]+", text.casefold()))
    roman_hi = {
        "kya", "kaise", "kese", "batao", "mujhe", "mera", "mere",
        "hai", "he", "nhi", "abhi", "karna", "karo", "wala",
    }
    if len(words & roman_hi) >= 2:
        return "roman-hi"
    return "en" if re.search(r"[A-Za-z]", text) else "other"


def analyze_intent(
    messages: list[dict[str, Any]],
    *,
    require_current: bool = False,
) -> IntelligencePlan:
    current = last_user_text(messages).strip()
    previous = _previous_user_text(messages).strip()
    low = current.casefold()

    is_followup = bool(current and len(current) <= 120 and _FOLLOWUP.match(current))
    classification_text = (
        f"{previous}\nCURRENT FOLLOW-UP: {current}" if is_followup and previous else current
    )
    q = classification_text.casefold()

    code = "```" in classification_text or any(token in q for token in _CODE)
    reasoning = any(token in q for token in _REASON) or bool(_MATH.search(classification_text))
    research = any(token in q for token in _RESEARCH)
    current_info = (
        require_current
        or any(token in q for token in _CURRENT)
        or bool(_YEAR.search(q) and any(x in q for x in ("latest", "current", "version", "news")))
    )
    image = any(token in q for token in _IMAGE)
    files = any(token in q for token in _FILE)
    calculator = bool(_MATH.search(classification_text)) or "calculate" in q

    large = (
        len(classification_text) > 1800
        or len(messages) > 18
        or any(
            token in q
            for token in (
                "complete code", "full code", "detailed report", "step by step",
                "all countries", "all states", "poori list", "puri list",
                "sabhi", "saare", "everything", "complete project",
            )
        )
    )

    if code:
        task = "code"
    elif reasoning:
        task = "reasoning"
    elif research or current_info:
        task = "research"
    elif any(low.startswith(token) for token in _SIMPLE):
        task = "simple"
    else:
        task = "general"

    fast_general = (
        task == "general"
        and len(current) <= 900
        and len(messages) <= 12
        and not current_info
        and not large
    )
    simple = task == "simple" and len(current) <= 180 and not large

    difficulty = (
        "low"
        if simple or fast_general
        else "high"
        if code or reasoning or research or large
        else "medium"
    )
    tier = "fast" if difficulty == "low" and not current_info else "strong"

    reasons: list[str] = []
    if is_followup:
        reasons.append("follow-up context inherited from previous user request")
    if code:
        reasons.append("coding/debugging intent detected")
    if reasoning:
        reasons.append("reasoning/calculation intent detected")
    if research:
        reasons.append("research/evidence intent detected")
    if current_info:
        reasons.append("fresh/current information required")
    if image:
        reasons.append("image-generation intent detected")
    if files:
        reasons.append("artifact/file intent detected")
    if large:
        reasons.append("large/complex request detected")
    if not reasons:
        reasons.append("general conversational request")

    explicit_signals = sum(
        int(x)
        for x in (code, reasoning, research, current_info, image, files, calculator, is_followup)
    )
    confidence = min(0.99, 0.74 + explicit_signals * 0.035)
    if not current:
        confidence = 0.35

    return IntelligencePlan(
        task_type=task,
        difficulty=difficulty,
        tier=tier,
        language=detect_language(current),
        needs_web=bool(current_info or research),
        needs_current=bool(current_info),
        needs_verification=bool(
            current_info
            or research
            or reasoning
            or code
            or any(x in q for x in ("exact", "accurate", "verify", "proof", "source"))
        ),
        needs_calculator=calculator,
        needs_code_agent=code and (large or any(x in q for x in ("fix", "debug", "repair", "project"))),
        needs_files=files,
        needs_image=image,
        is_followup=is_followup,
        confidence=round(confidence, 3),
        reasons=tuple(reasons),
    )
