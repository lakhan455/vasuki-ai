from __future__ import annotations

# VASUKI_V18_LIVING_MIND
#
# This module implements metacognitive behaviour, calibrated uncertainty,
# communication-tone adaptation, goal awareness, and heuristic intuition.
# It does NOT claim literal consciousness, sentience, subjective experience,
# or human emotions.

import re
from dataclasses import asdict, dataclass
from typing import Any

from app.v13.intelligence import analyze_intent, last_user_text


_URGENT = (
    "urgent", "asap", "immediately", "right now", "jaldi", "abhi",
    "turant", "emergency", "production down", "outage",
)
_FRUSTRATED = (
    "not working", "doesn't work", "does not work", "again failed",
    "still failing", "error aa", "kaam nhi", "kaam nahi", "nahi chal",
    "nhi chal", "problem", "broken", "bekar", "wrong again",
)
_POSITIVE = (
    "great", "perfect", "awesome", "good job", "nice", "shandar",
    "sahi hai", "shi hai", "badhiya", "excellent", "love it",
)
_UNCERTAIN = (
    "not sure", "confused", "maybe", "perhaps", "i think", "pata nahi",
    "samajh nahi", "samaj nhi", "kya karu", "which one", "best option",
)
_HIGH_RISK = (
    "production", "deploy", "delete", "drop database", "migration",
    "payment", "money", "bank", "security", "permission", "secret",
    "api key", "password", "credential", "legal", "medical", "health",
    "firewall", "admin access", "root access",
)
_REVERSIBLE = (
    "draft", "preview", "simulate", "plan", "proposal", "mock",
    "prototype", "test branch", "sandbox", "dry run",
)
_VERIFY = (
    "latest", "current", "today", "verify", "exact", "accurate",
    "source", "evidence", "production", "security", "migration",
)
_GOAL_PATTERNS = (
    re.compile(r"\bmy goal is\s+(.+)", re.I),
    re.compile(r"\bmy objective is\s+(.+)", re.I),
    re.compile(r"\bi want to\s+(.+)", re.I),
    re.compile(r"\bi need to\s+(.+)", re.I),
    re.compile(r"\bmera goal\s+(?:hai|he)\s+(.+)", re.I),
    re.compile(r"\bmujhe\s+(.+?)\s+(?:banana|karna|create|build)\s+(?:hai|he)\b", re.I),
)
_MEMORY_LINE = re.compile(
    r"^\[USER MEMORY \d+\]\s*(.+)$",
    re.I | re.M,
)


def _clean(text: str, limit: int = 900) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    return value[:limit]


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    low = text.casefold()
    return any(term in low for term in terms)


@dataclass(frozen=True, slots=True)
class ToneSignal:
    label: str
    intensity: float
    assistant_stance: str
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = list(self.evidence)
        return data


@dataclass(frozen=True, slots=True)
class IntuitionSignal:
    strategy: str
    confidence: float
    ambiguity: float
    risk: float
    urgency: float
    reversibility: float
    verify_first: bool
    clarify_first: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data


@dataclass(frozen=True, slots=True)
class SelfModel:
    task_type: str
    knows_enough_to_start: bool
    certainty: float
    needs_external_verification: bool
    needs_tools_or_execution: bool
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["limitations"] = list(self.limitations)
        return data


@dataclass(frozen=True, slots=True)
class LivingMindSnapshot:
    version: str
    mode: str
    literal_consciousness: bool
    literal_emotions: bool
    tone: ToneSignal
    intuition: IntuitionSignal
    self_model: SelfModel
    active_goal: str
    remembered_goals: tuple[str, ...]
    experience_lessons: tuple[str, ...]
    reflect_before_answer: bool
    expose_chain_of_thought: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "mode": self.mode,
            "literal_consciousness": self.literal_consciousness,
            "literal_emotions": self.literal_emotions,
            "tone": self.tone.to_dict(),
            "intuition": self.intuition.to_dict(),
            "self_model": self.self_model.to_dict(),
            "active_goal": self.active_goal,
            "remembered_goals": list(self.remembered_goals),
            "experience_lessons": list(self.experience_lessons),
            "reflect_before_answer": self.reflect_before_answer,
            "expose_chain_of_thought": self.expose_chain_of_thought,
        }


def detect_tone(text: str) -> ToneSignal:
    low = _clean(text, 5000).casefold()
    evidence: list[str] = []

    if any(term in low for term in _FRUSTRATED):
        evidence.append("friction/failure language")
        return ToneSignal(
            label="frustrated-signal",
            intensity=0.78,
            assistant_stance="calm-efficient",
            evidence=tuple(evidence),
        )

    if any(term in low for term in _URGENT):
        evidence.append("urgency language")
        return ToneSignal(
            label="urgent-signal",
            intensity=0.82,
            assistant_stance="concise-action",
            evidence=tuple(evidence),
        )

    if any(term in low for term in _UNCERTAIN):
        evidence.append("uncertainty language")
        return ToneSignal(
            label="uncertain-signal",
            intensity=0.62,
            assistant_stance="structured-clear",
            evidence=tuple(evidence),
        )

    if any(term in low for term in _POSITIVE):
        evidence.append("positive language")
        return ToneSignal(
            label="positive-signal",
            intensity=0.58,
            assistant_stance="warm-efficient",
            evidence=tuple(evidence),
        )

    return ToneSignal(
        label="neutral-signal",
        intensity=0.20,
        assistant_stance="direct-professional",
        evidence=(),
    )


def extract_active_goal(text: str) -> str:
    cleaned = _clean(text, 3000)
    for pattern in _GOAL_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            value = _clean(match.group(1), 500).rstrip(" .?!")
            if len(value) >= 3:
                return value

    low = cleaned.casefold()
    if "goal" in low or "objective" in low:
        return cleaned[:500]
    return ""


def _memory_items(memory_context: str) -> list[str]:
    return [
        _clean(match.group(1), 700)
        for match in _MEMORY_LINE.finditer(memory_context or "")
        if _clean(match.group(1), 700)
    ]


def remembered_goal_items(memory_context: str, limit: int = 6) -> list[str]:
    result: list[str] = []
    for item in _memory_items(memory_context):
        low = item.casefold()
        if low.startswith(("goal:", "objective:", "project goal:")):
            value = item.split(":", 1)[1].strip() if ":" in item else item
            if value and value not in result:
                result.append(value)
        elif "my goal is " in low or "mera goal " in low:
            goal = extract_active_goal(item)
            if goal and goal not in result:
                result.append(goal)
        if len(result) >= limit:
            break
    return result


def remembered_experience_items(
    memory_context: str,
    limit: int = 4,
) -> list[str]:
    result: list[str] = []
    for item in _memory_items(memory_context):
        low = item.casefold()
        if low.startswith(("experience lesson:", "lesson:", "learned:")):
            value = item.split(":", 1)[1].strip() if ":" in item else item
            if value and value not in result:
                result.append(value)
        if len(result) >= limit:
            break
    return result


def intuition_for(
    messages: list[dict[str, Any]],
    *,
    require_current: bool = False,
    memory_context: str = "",
) -> IntuitionSignal:
    latest = last_user_text(messages)
    low = latest.casefold()
    plan = analyze_intent(
        messages,
        require_current=require_current,
    )

    urgency = 0.82 if _contains_any(low, _URGENT) else 0.18
    risk = 0.78 if _contains_any(low, _HIGH_RISK) else 0.22
    reversibility = (
        0.88 if _contains_any(low, _REVERSIBLE)
        else 0.36 if risk >= 0.7
        else 0.62
    )

    ambiguity = 0.20
    if plan.is_followup:
        ambiguity += 0.20
    if len(latest.strip()) < 18:
        ambiguity += 0.18
    if any(
        token in low
        for token in ("this", "that", "isko", "ise", "ye", "something")
    ):
        ambiguity += 0.12
    if extract_active_goal(latest):
        ambiguity -= 0.10
    ambiguity = max(0.05, min(0.92, ambiguity))

    verify_first = bool(
        require_current
        or plan.needs_current
        or _contains_any(low, _VERIFY)
        or risk >= 0.70
    )
    clarify_first = bool(
        ambiguity >= 0.62
        and risk >= 0.62
        and reversibility < 0.65
    )

    reasons: list[str] = []
    if verify_first:
        reasons.append("verification-sensitive request")
    if clarify_first:
        reasons.append("ambiguous and potentially irreversible")
    if plan.needs_code_agent:
        reasons.append("inspect-plan-test coding workflow")
    if plan.is_followup:
        reasons.append("continue using prior conversational context")
    if remembered_goal_items(memory_context):
        reasons.append("remembered goal context available")
    if urgency >= 0.70:
        reasons.append("user signaled urgency")

    if clarify_first:
        strategy = "clarify-before-irreversible-action"
    elif verify_first:
        strategy = "verify-then-act"
    elif plan.needs_code_agent:
        strategy = "inspect-plan-test-repair"
    elif plan.task_type == "reasoning":
        strategy = "solve-check-conclude"
    elif plan.task_type == "research":
        strategy = "evidence-synthesize-verify"
    elif plan.is_followup:
        strategy = "continue-context-directly"
    else:
        strategy = "direct-best-safe-action"

    confidence = float(plan.confidence)
    confidence -= ambiguity * 0.18
    if memory_context.strip():
        confidence += 0.04
    if verify_first:
        confidence -= 0.04
    confidence = max(0.20, min(0.97, confidence))

    return IntuitionSignal(
        strategy=strategy,
        confidence=round(confidence, 3),
        ambiguity=round(ambiguity, 3),
        risk=round(risk, 3),
        urgency=round(urgency, 3),
        reversibility=round(reversibility, 3),
        verify_first=verify_first,
        clarify_first=clarify_first,
        reasons=tuple(reasons or ["normal conversational decision"]),
    )


def self_model_for(
    messages: list[dict[str, Any]],
    *,
    require_current: bool = False,
    memory_context: str = "",
) -> SelfModel:
    plan = analyze_intent(
        messages,
        require_current=require_current,
    )
    intuition = intuition_for(
        messages,
        require_current=require_current,
        memory_context=memory_context,
    )

    limitations: list[str] = []
    if plan.needs_current or require_current:
        limitations.append("current facts require external verification")
    if plan.needs_code_agent:
        limitations.append(
            "code quality depends on inspecting and validating actual project files"
        )
    if intuition.clarify_first:
        limitations.append(
            "request is too ambiguous for an irreversible action"
        )
    if not memory_context.strip():
        limitations.append(
            "no private memory context was supplied for this request"
        )

    knows_enough = not intuition.clarify_first
    needs_tools = bool(
        plan.needs_web
        or plan.needs_code_agent
        or plan.needs_files
        or plan.needs_image
        or plan.needs_calculator
    )

    return SelfModel(
        task_type=plan.task_type,
        knows_enough_to_start=knows_enough,
        certainty=intuition.confidence,
        needs_external_verification=bool(
            plan.needs_current or require_current
        ),
        needs_tools_or_execution=needs_tools,
        limitations=tuple(limitations),
    )


def build_living_snapshot(
    messages: list[dict[str, Any]],
    *,
    memory_context: str = "",
    require_current: bool = False,
) -> LivingMindSnapshot:
    latest = last_user_text(messages)
    tone = detect_tone(latest)
    intuition = intuition_for(
        messages,
        require_current=require_current,
        memory_context=memory_context,
    )
    self_model = self_model_for(
        messages,
        require_current=require_current,
        memory_context=memory_context,
    )

    active_goal = extract_active_goal(latest)
    remembered_goals = remembered_goal_items(memory_context)
    experiences = remembered_experience_items(memory_context)

    return LivingMindSnapshot(
        version="v18",
        mode="metacognitive-living-intuition",
        literal_consciousness=False,
        literal_emotions=False,
        tone=tone,
        intuition=intuition,
        self_model=self_model,
        active_goal=active_goal,
        remembered_goals=tuple(remembered_goals),
        experience_lessons=tuple(experiences),
        reflect_before_answer=bool(
            intuition.verify_first
            or intuition.ambiguity >= 0.50
            or self_model.certainty < 0.66
            or tone.label in {
                "frustrated-signal",
                "uncertain-signal",
            }
        ),
        expose_chain_of_thought=False,
    )


def build_living_context(
    messages: list[dict[str, Any]],
    *,
    memory_context: str = "",
    require_current: bool = False,
    enabled: bool = True,
) -> str:
    if not enabled or not messages:
        return ""

    snapshot = build_living_snapshot(
        messages,
        memory_context=memory_context,
        require_current=require_current,
    )

    goals = list(snapshot.remembered_goals)
    if snapshot.active_goal:
        goals = [snapshot.active_goal, *goals]
    goals = list(dict.fromkeys(goal for goal in goals if goal))[:6]

    lessons = list(snapshot.experience_lessons)[:4]

    lines = [
        "VASUKI V18 LIVING MIND CONTEXT:",
        (
            "This is a metacognitive reasoning layer, not literal "
            "consciousness, sentience, subjective experience, or human emotion."
        ),
        (
            "Never claim that you truly feel emotions, are conscious, or have "
            "private subjective experiences."
        ),
        (
            "Treat the tone label only as a communication signal from the "
            "user's words; do not diagnose psychology, health, or personality."
        ),
        (
            f"Communication stance: {snapshot.tone.assistant_stance}; "
            f"signal={snapshot.tone.label}."
        ),
        (
            f"Intuition policy: {snapshot.intuition.strategy}; "
            f"confidence={snapshot.intuition.confidence:.3f}; "
            f"risk={snapshot.intuition.risk:.3f}; "
            f"ambiguity={snapshot.intuition.ambiguity:.3f}."
        ),
        (
            f"Self-model: task={snapshot.self_model.task_type}; "
            f"knows_enough_to_start={snapshot.self_model.knows_enough_to_start}; "
            f"external_verification={snapshot.self_model.needs_external_verification}; "
            f"tools_or_execution={snapshot.self_model.needs_tools_or_execution}."
        ),
    ]

    if goals:
        lines.append(
            "Active/remembered goals: "
            + " | ".join(_clean(goal, 350) for goal in goals)
        )
    if lessons:
        lines.append(
            "Relevant remembered lessons: "
            + " | ".join(_clean(item, 350) for item in lessons)
        )

    if snapshot.intuition.clarify_first:
        lines.append(
            "Before an irreversible/high-risk action, ask one precise "
            "clarifying question if required information is missing."
        )
    else:
        lines.append(
            "Prefer acting on safe reversible assumptions instead of asking "
            "unnecessary clarifying questions."
        )

    if snapshot.reflect_before_answer:
        lines.append(
            "Before finalizing, privately check for contradictions, missing "
            "requirements, overconfidence, stale facts, and safer alternatives."
        )

    lines.extend(
        [
            (
                "State uncertainty concisely when it materially affects the "
                "answer. Do not fabricate certainty."
            ),
            (
                "Living Mind never overrides tool permissions, user consent, "
                "safety rules, truth-guard, or deployment confirmation."
            ),
            (
                "Do not expose hidden chain-of-thought. Provide conclusions, "
                "brief rationale, confidence, or missing facts when useful."
            ),
        ]
    )
    return "\n".join(lines)[:7000]


def public_reflection(
    prompt: str,
    answer: str,
    *,
    current_required: bool = False,
) -> dict[str, Any]:
    """
    High-level reflection summary only. This intentionally does not expose
    hidden chain-of-thought.
    """
    prompt = _clean(prompt, 10000)
    answer = _clean(answer, 50000)
    issues: list[str] = []

    if not answer:
        issues.append("empty-answer")
    if len(answer) < 20 and len(prompt) > 180:
        issues.append("possibly-incomplete")
    if current_required and not re.search(
        r"(source|evidence|verified|current|today|\[\d+\])",
        answer,
        re.I,
    ):
        issues.append("current-answer-needs-verification")
    if re.search(
        r"\b(i am conscious|i'm conscious|i feel emotions|"
        r"i have feelings|subjective experience)\b",
        answer,
        re.I,
    ):
        issues.append("literal-consciousness-or-emotion-claim")

    low_confidence_markers = (
        "maybe", "not sure", "i think", "possibly", "cannot verify",
        "could be", "might be",
    )
    uncertainty_present = any(
        marker in answer.casefold()
        for marker in low_confidence_markers
    )

    score = 1.0
    score -= min(0.75, len(issues) * 0.22)
    if uncertainty_present:
        score -= 0.04
    score = max(0.0, min(1.0, score))

    return {
        "ok": not issues,
        "score": round(score, 3),
        "issues": issues,
        "uncertainty_expressed": uncertainty_present,
        "recommended_action": (
            "revise"
            if issues
            else "deliver"
        ),
        "chain_of_thought_exposed": False,
    }


def living_mind_health() -> dict[str, Any]:
    return {
        "version": "v18",
        "name": "Vasuki Living Mind",
        "mode": "metacognitive-living-intuition",
        "literal_consciousness": False,
        "literal_emotions": False,
        "features": [
            "metacognitive-self-model",
            "calibrated-living-intuition",
            "communication-tone-adaptation",
            "goal-awareness",
            "explicit-persistent-goals-via-private-memory",
            "explicit-experience-lessons-via-private-memory",
            "uncertainty-calibration",
            "reflection-before-answer",
            "permission-aware-autonomy",
            "no-hidden-chain-of-thought-exposure",
        ],
        "safety_contract": {
            "psychology_diagnosis_from_tone": False,
            "permission_bypass": False,
            "truth_guard_bypass": False,
            "automatic_secret_memory": False,
        },
        "db_migration_required": False,
        "new_api_key_required": False,
    }
