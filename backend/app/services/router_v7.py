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
        "vasuki_cloud": bool(
            getattr(s, "vasuki_cloud_enabled", False)
            and (
                (
                    str(
                        getattr(
                            s,
                            "vasuki_cloud_transport",
                            "openai",
                        )
                        or "openai"
                    ).strip().casefold()
                    == "gradio"
                    and str(
                        getattr(
                            s,
                            "vasuki_cloud_space_id",
                            "",
                        )
                        or ""
                    ).strip()
                    and str(
                        getattr(
                            s,
                            "vasuki_cloud_gradio_api_name",
                            "/chat",
                        )
                        or ""
                    ).strip()
                )
                or (
                    str(
                        getattr(
                            s,
                            "vasuki_cloud_transport",
                            "openai",
                        )
                        or "openai"
                    ).strip().casefold()
                    == "openai"
                    and str(
                        getattr(
                            s,
                            "vasuki_cloud_base_url",
                            "",
                        )
                        or ""
                    ).strip()
                    and getattr(
                        s,
                        "vasuki_cloud_api_key",
                        None,
                    )
                    and str(
                        getattr(
                            s,
                            "vasuki_cloud_model",
                            "",
                        )
                        or ""
                    ).strip()
                )
            )
        ),
        "groq_fast": bool(getattr(s, "groq_api_key", None)),
        "groq": bool(getattr(s, "groq_api_key", None)),
        "sambanova": bool(getattr(s, "sambanova_api_key", None)),
        "cerebras": bool(getattr(s, "cerebras_api_key", None)),
        "gemini": bool(getattr(s, "google_gemini_api", None)),
        "opencode_zen": bool(getattr(s, "opencode_zen_api_key", None)),
        "zai_glm": bool(getattr(s, "zai_api_key", None)),
        "openrouter": bool(getattr(s, "openrouter_api", None)),
        "mistral": bool(getattr(s, "mistral_ai_api", None)),
    }.get(name, False)

def apply_auto_provider_policy(
    names: list[str],
    provider: str,
    settings: Any,
) -> list[str]:
    """Keep Vasuki Cloud controlled in auto routing.

    Explicit vasuki_cloud requests are unchanged.
    When auto-primary is disabled, Vasuki Cloud remains available
    but stays behind the existing configured providers.
    """
    ordered = list(dict.fromkeys(names))

    if provider != "auto":
        return ordered

    if bool(
        getattr(
            settings,
            "vasuki_cloud_auto_primary",
            False,
        )
    ):
        return ordered

    if "vasuki_cloud" not in ordered:
        return ordered

    return [
        name
        for name in ordered
        if name != "vasuki_cloud"
    ] + ["vasuki_cloud"]


def base_candidates(d: RoutingDecision, provider: str) -> list[str]:
    if provider != "auto":
        return [provider]

    if d.tier == "fast":
        return [
            "vasuki_cloud",
            "groq_fast",
            "cerebras",
            "mistral",
            "openrouter",
            "groq",
            "sambanova",
            "gemini",
        ]

    if d.task_type == "code":
        return [
            "opencode_zen",
            "zai_glm",
            "vasuki_cloud",
            "groq",
            "openrouter",
            "gemini",
            "mistral",
            "cerebras",
            "sambanova",
        ]

    if d.task_type in {"research", "reasoning"}:
        return [
            "vasuki_cloud",
            "groq",
            "gemini",
            "sambanova",
            "cerebras",
            "openrouter",
        ]

    return [
        "vasuki_cloud",
        "groq",
        "gemini",
        "openrouter",
        "sambanova",
        "cerebras",
    ]
