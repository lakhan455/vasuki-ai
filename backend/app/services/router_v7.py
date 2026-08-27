from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any
from app.config import Settings
from app.v13.intelligence import analyze_intent

_CODE = ("bug","debug","traceback","exception","typeerror","syntaxerror","optimize",
         "refactor","python","javascript","typescript","react","next.js","fastapi",
         "sql","html","css","flutter","kotlin","gradle")
_REASON = ("proof","prove","derive","equation","theorem","algorithm","logic",
           "reasoning","puzzle","calculate","solve","complexity")
_RESEARCH = ("research","compare","analysis","report","latest","current","today",
             "verify","sources","citation","evidence")
_SIMPLE = ("hi","hello","hey","thanks","thank you","good morning","good evening",
           "define ","meaning of ","translate ")

@dataclass(frozen=True, slots=True)
class RoutingDecision:
    task_type: str
    difficulty: str
    tier: str
    language: str
    needs_web: bool

def last_user_query(messages: list[dict[str, Any]]) -> str:
    return next((str(x.get("content") or "") for x in reversed(messages)
                 if x.get("role") == "user"), "")

def detect_language(text: str) -> str:
    if re.search(r"[\u0900-\u097F]", text): return "hi"
    words = set(re.findall(r"[a-z]+", text.casefold()))
    if len(words & {"kya","kaise","kese","batao","mujhe","mera","mere","hai","he","nhi","abhi"}) >= 2:
        return "roman-hi"
    return "en" if re.search(r"[A-Za-z]", text) else "other"

def classify_route(messages: list[dict[str, Any]], *, require_current: bool=False) -> RoutingDecision:
    plan = analyze_intent(messages, require_current=require_current)
    return RoutingDecision(
        task_type=plan.task_type,
        difficulty=plan.difficulty,
        tier=plan.tier,
        language=plan.language,
        needs_web=plan.needs_web,
    )

def configured_provider(name: str, s: Settings) -> bool:
    return {
        "groq_fast": bool(getattr(s, "groq_api_key", None)),
        "groq": bool(getattr(s, "groq_api_key", None)),
        "sambanova": bool(getattr(s, "sambanova_api_key", None)),
        "cerebras": bool(getattr(s, "cerebras_api_key", None)),
        "gemini": bool(getattr(s, "google_gemini_api", None)),
        "opencode_zen": bool(getattr(s, "opencode_zen_api_key", None)),
        "openrouter": bool(getattr(s, "openrouter_api", None)),
        "mistral": bool(getattr(s, "mistral_ai_api", None)),
    }.get(name, False)

def base_candidates(d: RoutingDecision, provider: str) -> list[str]:
    if provider != "auto": return [provider]
    if d.tier == "fast":
        return [
            "groq_fast",
            "cerebras",
            "mistral",
            "openrouter",
            "groq",
            "sambanova",
            "gemini",
        ]
    if d.task_type == "code": return ["opencode_zen","groq","openrouter","gemini","mistral","cerebras","sambanova"]
    if d.task_type in {"research","reasoning"}: return ["groq","gemini","sambanova","cerebras","openrouter"]
    return ["groq","gemini","openrouter","sambanova","cerebras"]
