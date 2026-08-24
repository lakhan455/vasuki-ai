from app.services.personal_memory import (
    explicit_memory_category,
    extract_explicit_memory,
    extract_explicit_memory_command,
)


def test_multiline_memory_then_followup_is_split():
    query = (
        "Remember that my goal is to make Vasuki AI a powerful "
        "autonomous AI assistant.\n\n"
        "Now tell me:\n"
        "1. What is my goal?\n"
        "2. What are you uncertain about?\n"
        "3. What should I improve next?"
    )

    memory, followup = extract_explicit_memory_command(query)

    assert memory == (
        "my goal is to make Vasuki AI a powerful autonomous AI assistant"
    )
    assert followup.startswith("Now tell me:")
    assert "What is my goal?" in followup


def test_flattened_memory_then_followup_is_split():
    query = (
        "Remember that I prefer concise answers. "
        "Now explain how provider recovery works."
    )

    memory, followup = extract_explicit_memory_command(query)

    assert memory == "I prefer concise answers"
    assert followup == "Now explain how provider recovery works."


def test_memory_only_keeps_old_behavior():
    memory, followup = extract_explicit_memory_command(
        "Remember that I prefer dark mode."
    )

    assert memory == "I prefer dark mode"
    assert followup == ""
    assert extract_explicit_memory(
        "Remember that I prefer dark mode."
    ) == "I prefer dark mode"


def test_goal_memory_gets_living_goal_category():
    assert (
        explicit_memory_category(
            "my goal is to make Vasuki AI more capable"
        )
        == "living_goal"
    )


def test_normal_sentence_with_now_is_not_accidentally_split():
    memory, followup = extract_explicit_memory_command(
        "Remember that I am working now on the Vasuki project."
    )

    assert memory == "I am working now on the Vasuki project"
    assert followup == ""


def test_non_memory_message_returns_none():
    memory, followup = extract_explicit_memory_command(
        "Tell me what my goal is."
    )

    assert memory is None
    assert followup == ""
