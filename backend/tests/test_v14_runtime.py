from app.v14.runtime import (
    decide_runtime,
    prepare_quality_messages,
    runtime_health,
    try_fast_calculation,
)


def test_v14_auto_web_for_fresh_verified_request():
    decision = decide_runtime([
        {
            "role": "user",
            "content": "Verify the latest Gemini API pricing today with sources.",
        }
    ])
    assert decision.auto_web is True
    assert decision.intelligence.needs_current is True


def test_v14_does_not_auto_web_for_simple_chat():
    decision = decide_runtime([
        {"role": "user", "content": "Hello, how are you?"}
    ])
    assert decision.auto_web is False


def test_v14_fast_calculator_is_deterministic():
    result = try_fast_calculation("calculate 24 * 6")
    assert result is not None
    assert result["result"] == 144
    assert "144" in result["answer"]


def test_v14_fast_calculator_rejects_non_math_text():
    assert try_fast_calculation(
        "Write Python code that multiplies 24 and 6"
    ) is None


def test_v14_quality_contract_added_for_code():
    rows = prepare_quality_messages([
        {
            "role": "user",
            "content": "Fix this FastAPI bug and give complete code.",
        }
    ])
    assert rows[0]["role"] == "system"
    assert rows[0]["content"].startswith(
        "VASUKI V14 RESPONSE CONTRACT:"
    )
    assert "Do not invent" in rows[0]["content"]


def test_v14_quality_contract_is_not_duplicated():
    rows = prepare_quality_messages([
        {
            "role": "system",
            "content": "VASUKI V14 RESPONSE CONTRACT: old",
        },
        {
            "role": "user",
            "content": "Solve 2 + 2 and verify the result.",
        },
    ])
    contracts = [
        item
        for item in rows
        if item["role"] == "system"
        and item["content"].startswith(
            "VASUKI V14 RESPONSE CONTRACT:"
        )
    ]
    assert len(contracts) == 1


def test_v14_runtime_health_has_no_migration_requirement():
    health = runtime_health()
    assert health["version"] == "v14"
    assert health["db_migration_required"] is False
    assert health["new_api_key_required"] is False
