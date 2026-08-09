from app.services.context_v8 import compact_messages_v8
from app.services.memory_v8 import normalize_memory_text


def test_memory_normalization_deduplicates_spacing_case_punctuation():
    assert normalize_memory_text("  My   Project Is Vasuki AI. ") == normalize_memory_text(
        "my project is vasuki ai"
    )


def test_context_v8_keeps_latest_and_project_digest():
    messages = [
        {"role": "user", "content": f"Vasuki project decision {i}: keep provider auto."}
        for i in range(14)
    ]
    compacted, stats = compact_messages_v8(
        messages,
        max_chars=20000,
        max_single_message_chars=4000,
    )
    joined = "\n".join(str(x.get("content") or "") for x in compacted)
    assert "Vasuki project decision 13" in joined
    assert "CONVERSATION STATE DIGEST" in joined
    assert stats.omitted_messages > 0
