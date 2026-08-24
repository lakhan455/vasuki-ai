from app.v13.context import compress_messages
from app.v13.deployment import check_deployment
from app.v13.image_identity import build_identity_locked_prompt, extract_image_constraints
from app.v13.intelligence import analyze_intent
from app.v13.verification import verify_answer


def test_followup_inherits_previous_intent():
    plan = analyze_intent([
        {"role": "user", "content": "Fix this Python FastAPI traceback and update the code."},
        {"role": "assistant", "content": "Show me the traceback."},
        {"role": "user", "content": "haan karo"},
    ])
    assert plan.is_followup is True
    assert plan.task_type == "code"
    assert plan.tier == "strong"


def test_current_request_requires_web_and_verification():
    plan = analyze_intent([{"role": "user", "content": "What is the latest current Gemini API pricing today?"}])
    assert plan.task_type == "research"
    assert plan.needs_web is True
    assert plan.needs_current is True
    assert plan.needs_verification is True


def test_image_constraints_lock_model_and_color():
    prompt = "Create a black BMW M4 G82 two-door coupe on a mountain road."
    constraints = extract_image_constraints(prompt)
    assert "black" in constraints.colors
    assert constraints.vehicle_model.lower().startswith("bmw m4")
    locked = build_identity_locked_prompt(prompt, "realistic", "photorealistic photography")
    assert "COLOR LOCK" in locked
    assert "VEHICLE MODEL LOCK" in locked
    assert "do not inherit" in locked


def test_long_image_prompt_keeps_hard_constraints():
    prompt = ("Create a black BMW M4 G82. " + ("very detailed scene " * 150)).strip()
    locked = build_identity_locked_prompt(prompt, "realistic", "photorealistic")
    assert len(locked) <= 2048
    assert "COLOR LOCK" in locked
    assert "VEHICLE MODEL LOCK" in locked


def test_context_compression_preserves_recent_messages():
    rows = [
        {"role": "user", "content": "old " * 5000},
        {"role": "assistant", "content": "reply " * 3000},
        {"role": "user", "content": "latest instruction must survive"},
    ]
    compacted = compress_messages(rows, max_chars=2500, preserve_last=2)
    assert compacted[-1]["content"] == "latest instruction must survive"
    assert sum(len(x["content"]) for x in compacted) <= 3000


def test_verifier_flags_current_answer_without_sources():
    result = verify_answer(
        "What is the latest price today?",
        "The latest price is $99 in 2026.",
        sources=[],
        current_required=True,
    )
    assert result.score < 80
    assert result.hallucination_risk > 20


def test_deployment_guard_blocks_secret_env_and_unbacked_migration():
    result = check_deployment(
        ["backend/.env", "backend/supabase/new.sql"],
        tests_passed=True,
        backup_ready=False,
        pending_migrations=["new.sql"],
    )
    assert result.ready is False
    assert result.blockers
