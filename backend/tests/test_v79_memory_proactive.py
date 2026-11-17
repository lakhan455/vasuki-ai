from app.v79.memory_vector import novel_memory_context, short_term_window


def test_short_term_window_keeps_last_ten_messages():
    messages = [
        {
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"message {i}",
        }
        for i in range(15)
    ]

    result = short_term_window(
        messages,
        limit=10,
    )

    assert len(result) == 10
    assert result[0]["content"] == "message 5"
    assert result[-1]["content"] == "message 14"


def test_short_term_window_ignores_unknown_roles_and_empty_content():
    result = short_term_window(
        [
            {
                "role": "tool",
                "content": "hidden",
            },
            {
                "role": "user",
                "content": "   hello   world   ",
            },
            {
                "role": "assistant",
                "content": "",
            },
        ],
        limit=10,
    )

    assert result == [
        {
            "role": "user",
            "content": "hello world",
        }
    ]

def test_novel_memory_context_skips_existing_v74_memory():
    base_context = (
        "Known user preference: "
        "mera preferred backend framework FastAPI hai"
    )

    items = [
        {
            "memory_text": (
                "mera preferred backend framework FastAPI hai"
            )
        },
        {
            "memory_text": (
                "user prefers dark mode for dashboards"
            )
        },
    ]

    result = novel_memory_context(
        base_context,
        items,
    )

    assert "FastAPI" not in result
    assert "dark mode" in result
