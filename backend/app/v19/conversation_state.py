from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from app.v13.intelligence import analyze_intent, last_user_text

_FOLLOW = re.compile(r"^(?:ok|okay|haan|ha|yes|karo|kar do|continue|aage|next|isko|ise|fix karo)(?:\s+.*)?$", re.I)
_CONSTRAINT = re.compile(r"\b(?:must|should|without|do not|don't|only|exactly|keep|preserve|avoid|no migration|no api key|no new key)\b", re.I)
_GOAL = re.compile(r"\b(?:goal|objective|mission|target|want to|need to|mujhe|mera goal)\b", re.I)


@dataclass(frozen=True, slots=True)
class ConversationState:
    version: str
    latest_request: str
    inherited_request: str
    active_request: str
    language: str
    is_followup: bool
    constraints: tuple[str, ...]
    goal_signal: bool
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["constraints"] = list(self.constraints)
        return data


def _user_messages(messages: list[dict[str, Any]]) -> list[str]:
    return [
        str(item.get("content") or "").strip()
        for item in messages
        if item.get("role") == "user" and str(item.get("content") or "").strip()
    ]


def resolve_conversation_state(messages: list[dict[str, Any]]) -> ConversationState:
    users = _user_messages(messages)
    latest = last_user_text(messages).strip()
    previous = users[-2] if len(users) >= 2 else ""
    plan = analyze_intent(messages, require_current=False)
    follow = bool(plan.is_followup or (latest and len(latest) <= 140 and _FOLLOW.match(latest)))
    inherited = previous if follow else ""
    active = f"{previous}\nCURRENT FOLLOW-UP: {latest}".strip() if follow and previous else latest

    constraints: list[str] = []
    for source in users[-6:]:
        if _CONSTRAINT.search(source):
            clean = re.sub(r"\s+", " ", source).strip()
            if clean not in constraints:
                constraints.append(clean[:500])

    return ConversationState(
        version="v19.3",
        latest_request=latest,
        inherited_request=inherited,
        active_request=active,
        language=plan.language,
        is_followup=follow,
        constraints=tuple(constraints[-6:]),
        goal_signal=bool(_GOAL.search(active)),
        confidence=min(0.99, round(plan.confidence + (0.04 if follow and previous else 0), 3)),
    )


def conversation_state_health() -> dict[str, Any]:
    return {
        "version": "v19.3",
        "name": "Conversation State Resolver",
        "features": [
            "latest-turn-priority",
            "short-followup-inheritance",
            "recent-constraint-capture",
            "goal-signal-detection",
            "no-silent-persistence",
        ],
        "db_migration_required": False,
        "new_api_key_required": False,
        "extra_provider_call_required": False,
    }
