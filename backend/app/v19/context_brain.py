from __future__ import annotations

# VASUKI_V19_CONTEXT_BRAIN
# Deterministic intent/context policy for normal chat.

import re
from dataclasses import asdict, dataclass
from typing import Any

from app.v13.intelligence import analyze_intent, last_user_text

_STRONG_CURRENT = re.compile(
    r"\b(?:latest|current|today|right now|currently|recent|news|this week|"
    r"this month|live score|stock price|exchange rate|weather|price today|"
    r"release date|latest version|current version|who is the current)\b",
    re.I,
)
_EXPLICIT_WEB = re.compile(
    r"\b(?:search (?:the )?web|search online|browse (?:the )?web|"
    r"look (?:it )?up online|check online|internet search|web search|use web|"
    r"use the web|find online sources|give citations|with citations|with sources)\b",
    re.I,
)
_PERSONAL_META = re.compile(
    r"\b(?:what is my goal|what(?:'s| is) my goal|my goal|my objective|"
    r"what do you remember|remember about me|what do you know about me|"
    r"what are you uncertain about|what should i improve|what should we improve|"
    r"what should vasuki improve|our goal|project goal|my preference|my preferences|"
    r"what did i say|what did we decide)\b",
    re.I,
)
_ADVICE_OR_HYPOTHETICAL = re.compile(
    r"\b(?:what should|what would|how should|how would|should i|would you|"
    r"before changing|before deploying|before production|improve next|best practice|"
    r"best practices|roadmap|architecture advice|what to verify|what would you verify)\b",
    re.I,
)
_SHORT_REFERENCE = re.compile(
    r"\b(?:this|that|it|these|those|same|isko|ise|ye|woh|usko|"
    r"fix karo|kar do|karo|continue|aage|next)\b",
    re.I,
)


def _clean(value: str, limit: int = 700) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _previous_user_text(messages: list[dict[str, Any]]) -> str:
    seen = 0
    for item in reversed(messages):
        if item.get("role") != "user":
            continue
        seen += 1
        if seen == 2:
            return _clean(str(item.get("content") or ""), 700)
    return ""


def _message_rows(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in messages:
        role = str(item.get("role") or "")
        content = str(item.get("content") or "")
        if role in {"user", "assistant", "system"} and content.strip():
            rows.append({"role": role, "content": content})
    return rows


@dataclass(frozen=True, slots=True)
class ContextDecision:
    version: str
    primary_intent: str
    task_type: str
    language: str
    confidence: float
    is_followup: bool
    personal_or_memory_context: bool
    advice_or_hypothetical: bool
    explicit_web_requested: bool
    strong_current_signal: bool
    allow_web: bool
    require_current: bool
    web_reason: str
    reference_text: str
    active_project: bool
    context_priority: tuple[str, ...]
    answer_policy: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["context_priority"] = list(self.context_priority)
        data["answer_policy"] = list(self.answer_policy)
        return data


def decide_context(
    messages: list[dict[str, Any]],
    *,
    explicit_web: bool = False,
    research_mode: bool = False,
    project_id: str = "",
) -> ContextDecision:
    rows = _message_rows(messages)
    current = _clean(last_user_text(rows), 6000)
    low = current.casefold()
    plan = analyze_intent(rows, require_current=research_mode)

    personal = bool(_PERSONAL_META.search(current))
    advice = bool(_ADVICE_OR_HYPOTHETICAL.search(current))
    explicit_web_signal = bool(explicit_web or _EXPLICIT_WEB.search(current))
    strong_current = bool(_STRONG_CURRENT.search(current))

    if research_mode:
        allow_web = True
        require_current = True
        web_reason = "research-mode-explicit"
    elif explicit_web_signal:
        allow_web = True
        require_current = strong_current
        web_reason = "user-explicitly-requested-web"
    elif strong_current:
        allow_web = True
        require_current = True
        web_reason = "freshness-sensitive-fact"
    elif personal or advice:
        allow_web = False
        require_current = False
        web_reason = "private-context-or-advice-no-web"
    elif plan.task_type == "research":
        allow_web = True
        require_current = bool(plan.needs_current)
        web_reason = "research-intent"
    elif plan.needs_current:
        allow_web = True
        require_current = True
        web_reason = "current-information-required"
    else:
        allow_web = False
        require_current = False
        web_reason = "conversation-context-sufficient"

    previous = _previous_user_text(rows)
    reference_text = ""
    if previous and (
        plan.is_followup
        or (len(current) <= 180 and bool(_SHORT_REFERENCE.search(low)))
    ):
        reference_text = previous

    if personal:
        primary_intent = "personal-context"
    elif plan.task_type == "code":
        primary_intent = "coding"
    elif research_mode or plan.task_type == "research":
        primary_intent = "research"
    elif advice:
        primary_intent = "advice"
    elif plan.task_type == "reasoning":
        primary_intent = "reasoning"
    elif plan.task_type == "simple":
        primary_intent = "simple-conversation"
    else:
        primary_intent = "general"

    priorities = ["current-conversation"]
    if str(project_id or "").strip():
        priorities.append("active-project")
    priorities.extend(["private-memory", "user-documents", "verified-web-evidence"])

    policies = [
        "answer-latest-user-intent-first",
        "resolve-short-references-from-conversation",
        "do-not-invent-citations",
        "do-not-insert-logos-or-images-unless-requested",
    ]
    if personal:
        policies.append("private-context-before-external-web")
    if not allow_web:
        policies.append("suppress-irrelevant-web-and-citations")
    if plan.task_type == "code":
        policies.append("preserve-existing-code-interfaces-before-changing")

    confidence = float(plan.confidence)
    if personal or advice or strong_current or explicit_web_signal:
        confidence = min(0.99, confidence + 0.06)
    if reference_text:
        confidence = min(0.99, confidence + 0.03)

    return ContextDecision(
        version="v19",
        primary_intent=primary_intent,
        task_type=plan.task_type,
        language=plan.language,
        confidence=round(confidence, 3),
        is_followup=bool(plan.is_followup),
        personal_or_memory_context=personal,
        advice_or_hypothetical=advice,
        explicit_web_requested=explicit_web_signal,
        strong_current_signal=strong_current,
        allow_web=allow_web,
        require_current=require_current,
        web_reason=web_reason,
        reference_text=reference_text,
        active_project=bool(str(project_id or "").strip()),
        context_priority=tuple(priorities),
        answer_policy=tuple(policies),
    )


def build_context_brain_context(
    messages: list[dict[str, Any]],
    *,
    explicit_web: bool = False,
    research_mode: bool = False,
    project_id: str = "",
) -> str:
    decision = decide_context(
        messages,
        explicit_web=explicit_web,
        research_mode=research_mode,
        project_id=project_id,
    )
    lines = [
        "VASUKI V19 INTENT & CONTEXT BRAIN:",
        f"Primary intent={decision.primary_intent}; task={decision.task_type}; confidence={decision.confidence:.3f}.",
        "Context priority: " + " > ".join(decision.context_priority) + ".",
        f"Web policy: allow={decision.allow_web}; require_current={decision.require_current}; reason={decision.web_reason}.",
        "Answer the user's latest real intent first. Resolve short phrases such as 'this', 'it', 'isko', 'same', or 'fix karo' from the current conversation before asking the user to repeat context.",
        "Do not insert a logo, image, media link, or decorative external asset unless the user explicitly requested one.",
        "Do not invent citations or attach unrelated sources. Cite web or document evidence only when such evidence was actually supplied and materially supports the answer.",
    ]
    if decision.reference_text:
        lines.append("Likely follow-up reference: " + _clean(decision.reference_text, 550))
    if decision.personal_or_memory_context:
        lines.append("This is a personal/context-memory request. Prefer current conversation and private memory. Do not use external web evidence unless the user explicitly asks for external/current facts.")
    if decision.advice_or_hypothetical and not decision.strong_current_signal:
        lines.append("This is advice/hypothetical reasoning, not a request to verify a current external fact. Words like 'verify' or 'production' alone must not trigger web research.")
    if decision.task_type == "code":
        lines.append("For coding follow-ups, preserve existing interfaces and resolve references against the active project/repository context before proposing broad rewrites.")
    lines.append("V19 does not override safety rules, truth guard, permissions, user consent, or deployment confirmation.")
    return "\n".join(lines)[:5200]


def context_brain_health() -> dict[str, Any]:
    return {
        "version": "v19",
        "name": "Vasuki Intent & Context Brain",
        "features": [
            "intent-aware-context-priority",
            "personal-memory-web-suppression",
            "advice-vs-current-fact-separation",
            "explicit-web-respect",
            "freshness-sensitive-web-routing",
            "short-followup-reference-resolution",
            "irrelevant-citation-suppression",
            "unrequested-logo-image-guard",
            "coding-context-preservation-policy",
        ],
        "context_priority": [
            "current-conversation",
            "active-project",
            "private-memory",
            "user-documents",
            "verified-web-evidence",
        ],
        "db_migration_required": False,
        "new_api_key_required": False,
        "extra_provider_call_required": False,
        "silent_memory_write": False,
        "hidden_chain_of_thought_exposed": False,
    }
