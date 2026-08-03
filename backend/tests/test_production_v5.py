from __future__ import annotations

from app.services.chat_v5 import build_resume_messages
from app.services.memory_v5 import memory_slot
from app.services.quota_v5 import _parse_rpc_payload


def test_memory_slot_detects_address_preference() -> None:
    assert memory_slot("Mujhe hamesha papa bolo") == "address_name"
    assert memory_slot('Call me "Boss"') == "address_name"


def test_memory_slot_detects_language_and_style() -> None:
    assert memory_slot("Always reply in Hindi") == "reply_language"
    assert memory_slot("Hamesha short jawab do") == "answer_style"


def test_quota_rpc_payload_parser() -> None:
    assert _parse_rpc_payload(
        [{"allowed": True, "message_count": 12, "daily_remaining": 238}]
    ) == (True, 12, 238)


def test_resume_messages_preserve_partial_answer() -> None:
    original = [{"role": "user", "content": "Complete code do"}]
    result = build_resume_messages(original, "partial output")
    assert result[-2] == {
        "role": "assistant",
        "content": "partial output",
    }
    assert "Do not repeat" in result[-1]["content"]
