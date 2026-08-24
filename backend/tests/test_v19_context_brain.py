from pathlib import Path

from app.v19.context_brain import (
    build_context_brain_context,
    context_brain_health,
    decide_context,
)


def msg(text: str):
    return [{"role": "user", "content": text}]


def test_personal_goal_question_suppresses_web():
    decision = decide_context(msg("What is my goal and what should I improve next?"))
    assert decision.personal_or_memory_context is True
    assert decision.allow_web is False
    assert decision.require_current is False


def test_hypothetical_verify_production_does_not_auto_web():
    decision = decide_context(msg("What would you verify before changing production?"))
    assert decision.advice_or_hypothetical is True
    assert decision.allow_web is False
    assert decision.web_reason == "private-context-or-advice-no-web"


def test_current_fact_still_requires_web():
    decision = decide_context(msg("What is the latest stable Next.js version today?"))
    assert decision.strong_current_signal is True
    assert decision.allow_web is True
    assert decision.require_current is True


def test_explicit_web_request_is_respected():
    decision = decide_context(msg("Search the web and give me sources about Python packaging."))
    assert decision.explicit_web_requested is True
    assert decision.allow_web is True


def test_research_request_can_use_web():
    decision = decide_context(msg("Research battery recycling methods and compare the evidence."))
    assert decision.allow_web is True
    assert decision.primary_intent == "research"


def test_short_followup_resolves_previous_user_reference():
    messages = [
        {"role": "user", "content": "My FastAPI login endpoint returns 500 after deploy."},
        {"role": "assistant", "content": "Please share the traceback."},
        {"role": "user", "content": "isko fix karo"},
    ]
    decision = decide_context(messages)
    assert decision.reference_text.startswith("My FastAPI login endpoint returns 500")
    assert decision.is_followup is True


def test_project_is_prioritized_before_memory_and_web():
    decision = decide_context(msg("fix this bug"), project_id="vasuki-ai")
    assert decision.context_priority[:3] == (
        "current-conversation",
        "active-project",
        "private-memory",
    )


def test_context_contains_citation_and_logo_guards():
    context = build_context_brain_context(msg("What is my goal?"))
    assert "Do not insert a logo" in context
    assert "Do not invent citations" in context
    assert "private memory" in context.casefold()


def test_health_contract_has_no_migration_or_key():
    health = context_brain_health()
    assert health["version"] == "v19"
    assert health["db_migration_required"] is False
    assert health["new_api_key_required"] is False
    assert health["extra_provider_call_required"] is False


def test_main_v11_contains_v19_production_monkeypatches():
    backend = Path(__file__).resolve().parents[1]
    source = (backend / "app" / "main_v11.py").read_text(encoding="utf-8")
    assert "VASUKI_V19_INTENT_CONTEXT_BRAIN_INTEGRATION" in source
    assert "v10.legacy._web_context = _v19_web_context" in source
    assert "v10.legacy._private_context = _v19_private_context" in source
    assert '@app.get("/health/v19")' in source
