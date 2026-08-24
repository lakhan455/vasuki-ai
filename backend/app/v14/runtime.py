from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from app.v11.agents import safe_calculate
from app.v13.intelligence import IntelligencePlan, analyze_intent

_AUTO_WEB_SIGNAL = re.compile(
    r"\b(?:latest|current|today|right now|currently|recent|news|this week|"
    r"this month|price|pricing|release date|latest version|sources?|citations?|"
    r"evidence|verify|verification|fact check|deep research|research report)\b",
    re.I,
)

_CALC_PREFIX = re.compile(
    r"^\s*(?:(?:calculate|compute|solve|what\s+is|find|kitna\s+hai|"
    r"kitna\s+hoga|hisab\s+karo)\s*[:\-]?\s*)",
    re.I,
)

_ALLOWED_CALC = re.compile(r"^[0-9\s().+\-*/]+$")


@dataclass(frozen=True, slots=True)
class RuntimeDecision:
    intelligence: IntelligencePlan
    auto_web: bool
    fast_calculation: bool
    calculation_expression: str
    quality_contract: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["intelligence"] = self.intelligence.to_dict()
        data["reasons"] = list(self.reasons)
        return data


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    return next(
        (
            str(item.get("content") or "").strip()
            for item in reversed(messages)
            if item.get("role") == "user"
        ),
        "",
    )


def _calculation_expression(text: str) -> str:
    raw = str(text or "").strip().rstrip(" ?")
    if not raw or len(raw) > 140:
        return ""

    candidate = _CALC_PREFIX.sub("", raw, count=1)
    candidate = (
        candidate.replace("×", "*")
        .replace("÷", "/")
        .replace("^", "**")
        .strip()
    )

    if not candidate or not _ALLOWED_CALC.fullmatch(candidate):
        return ""
    if not re.search(r"\d", candidate):
        return ""
    if not re.search(r"[+\-*/]", candidate):
        return ""
    return candidate


def try_fast_calculation(text: str) -> dict[str, Any] | None:
    expression = _calculation_expression(text)
    if not expression:
        return None

    try:
        value = safe_calculate(expression)
    except Exception:
        return None

    if isinstance(value, float) and value.is_integer():
        value = int(value)

    return {
        "expression": expression,
        "result": value,
        "answer": f"The result is **{value}**.",
    }


def _quality_contract(plan: IntelligencePlan, *, has_web_context: bool) -> str:
    if (
        plan.task_type in {"simple", "general"}
        and not plan.needs_verification
        and not plan.needs_current
    ):
        return ""

    rules = [
        "VASUKI V14 RESPONSE CONTRACT:",
        "Follow the user's latest instruction, requested format, and language.",
        "Do not invent tool executions, tests, files, citations, URLs, or capabilities.",
        "Do not silently claim that code was run or deployed unless execution evidence is actually provided.",
    ]

    if plan.task_type == "code":
        rules.extend(
            [
                "For coding tasks, preserve existing public interfaces unless the user asks to change them.",
                "Prefer targeted, runnable changes and call out assumptions that affect correctness.",
                "Check imports, names, edge cases, and likely regression points before finalizing.",
            ]
        )

    if plan.task_type in {"research", "reasoning"} or plan.needs_current:
        rules.append(
            "Separate verified facts from inference and do not fill evidence gaps with guesses."
        )

    if plan.needs_current:
        if has_web_context:
            rules.append(
                "Freshness-sensitive claims must be grounded in the supplied live context; if the context does not support a claim, say it cannot be verified."
            )
        else:
            rules.append(
                "Current information is required but no live evidence is present; do not guess current facts."
            )

    if plan.task_type == "reasoning" or plan.needs_calculator:
        rules.append(
            "Independently check the final calculation or logical conclusion before answering."
        )

    if plan.is_followup:
        rules.append(
            "Resolve short follow-up wording against the immediately preceding user intent without reintroducing superseded attributes."
        )

    return " ".join(rules)[:1800]


def decide_runtime(
    messages: list[dict[str, Any]],
    *,
    require_current: bool = False,
    web_context: str = "",
) -> RuntimeDecision:
    plan = analyze_intent(messages, require_current=require_current)
    query = _last_user_text(messages)
    calc = try_fast_calculation(query)

    auto_web = bool(
        plan.needs_current
        or (
            plan.needs_web
            and bool(_AUTO_WEB_SIGNAL.search(query))
        )
    )

    reasons = list(plan.reasons)
    if auto_web:
        reasons.append("V14 auto-web evidence policy activated")
    if calc:
        reasons.append("V14 deterministic calculator can answer directly")

    contract = _quality_contract(
        plan,
        has_web_context=bool(str(web_context or "").strip()),
    )
    if contract:
        reasons.append("V14 quality contract added for provider response")

    return RuntimeDecision(
        intelligence=plan,
        auto_web=auto_web,
        fast_calculation=bool(calc),
        calculation_expression=str(calc.get("expression") if calc else ""),
        quality_contract=contract,
        reasons=tuple(reasons),
    )


def prepare_quality_messages(
    messages: list[dict[str, Any]],
    *,
    require_current: bool = False,
    web_context: str = "",
) -> list[dict[str, Any]]:
    rows = [
        {**item, "content": str(item.get("content") or "")}
        for item in messages
    ]
    decision = decide_runtime(
        rows,
        require_current=require_current,
        web_context=web_context,
    )
    contract = decision.quality_contract
    if not contract:
        return rows

    clean = [
        item
        for item in rows
        if not (
            item.get("role") == "system"
            and str(item.get("content") or "").startswith(
                "VASUKI V14 RESPONSE CONTRACT:"
            )
        )
    ]
    return [
        {"role": "system", "content": contract},
        *clean,
    ]


def runtime_health() -> dict[str, Any]:
    return {
        "version": "v14",
        "features": [
            "smart-auto-web-policy",
            "deterministic-fast-calculator",
            "quality-contract-injection",
            "selective-answer-auto-repair",
            "moderation-safe-provider-recovery",
            "identity-critical-pro-image-upgrade",
        ],
        "db_migration_required": False,
        "new_api_key_required": False,
    }
