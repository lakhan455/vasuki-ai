from __future__ import annotations

from app.v18.living_mind import (
    build_living_context,
    build_living_snapshot,
    detect_tone,
    public_reflection,
    remembered_goal_items,
)


def _messages(text: str):
    return [{"role": "user", "content": text}]


def test_living_mind_never_claims_literal_consciousness():
    snap = build_living_snapshot(
        _messages("Help me plan a project"),
    )
    assert snap.literal_consciousness is False
    assert snap.literal_emotions is False
    assert snap.expose_chain_of_thought is False


def test_tone_is_communication_signal_not_psychology_claim():
    tone = detect_tone(
        "This is still not working, fix the error."
    )
    assert tone.label == "frustrated-signal"
    assert tone.assistant_stance == "calm-efficient"


def test_high_risk_request_uses_verify_first_intuition():
    snap = build_living_snapshot(
        _messages(
            "Deploy this production database migration now."
        ),
    )
    assert snap.intuition.verify_first is True
    assert snap.intuition.risk >= 0.7
    assert snap.intuition.strategy in {
        "verify-then-act",
        "clarify-before-irreversible-action",
    }


def test_goal_memory_is_detected_without_db_changes():
    memory = (
        "PRIVATE USER MEMORY:\n"
        "[USER MEMORY 1] Goal: Finish Vasuki V18 safely\n"
        "[USER MEMORY 2] Likes concise answers"
    )
    goals = remembered_goal_items(memory)
    assert goals == ["Finish Vasuki V18 safely"]


def test_context_contains_safety_and_goal_awareness():
    memory = (
        "PRIVATE USER MEMORY:\n"
        "[USER MEMORY 1] Goal: Ship Vasuki AI"
    )
    context = build_living_context(
        _messages("Continue the project"),
        memory_context=memory,
    )
    assert "not literal consciousness" in context.lower()
    assert "Ship Vasuki AI" in context
    assert "Do not expose hidden chain-of-thought" in context


def test_public_reflection_flags_false_consciousness_claim():
    result = public_reflection(
        "Are you conscious?",
        "I am conscious and I feel emotions.",
    )
    assert result["ok"] is False
    assert "literal-consciousness-or-emotion-claim" in result["issues"]
    assert result["chain_of_thought_exposed"] is False


def test_low_risk_direct_request_does_not_force_clarification():
    snap = build_living_snapshot(
        _messages("Write a short welcome email for my customer."),
    )
    assert snap.intuition.clarify_first is False
    assert snap.self_model.knows_enough_to_start is True
