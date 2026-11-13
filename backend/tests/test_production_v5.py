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


def test_simple_chat_can_skip_remote_context():
    from types import SimpleNamespace

    from app.main_v5 import (
        _should_skip_simple_context,
    )

    request = SimpleNamespace(
        use_web=False,
        use_documents=False,
        document_ids=[],
        project_id=None,
        research_mode=False,
    )

    assert _should_skip_simple_context(
        [
            {
                "role": "user",
                "content": "hii",
            }
        ],
        request,
    ) is True


def test_general_memory_sensitive_chat_keeps_context():
    from types import SimpleNamespace

    from app.main_v5 import (
        _should_skip_simple_context,
    )

    request = SimpleNamespace(
        use_web=False,
        use_documents=False,
        document_ids=[],
        project_id=None,
        research_mode=False,
    )

    assert _should_skip_simple_context(
        [
            {
                "role": "user",
                "content": "What is my name?",
            }
        ],
        request,
    ) is False


def test_project_chat_never_skips_context():
    from types import SimpleNamespace

    from app.main_v5 import (
        _should_skip_simple_context,
    )

    request = SimpleNamespace(
        use_web=False,
        use_documents=False,
        document_ids=[],
        project_id="project-1",
        research_mode=False,
    )

    assert _should_skip_simple_context(
        [
            {
                "role": "user",
                "content": "hii",
            }
        ],
        request,
    ) is False


def test_auth_cache_ttl_is_bounded():
    from types import SimpleNamespace

    from app.auth import _cache_ttl_seconds

    assert _cache_ttl_seconds(
        SimpleNamespace(
            auth_cache_ttl_seconds=300,
        )
    ) == 300.0

    assert _cache_ttl_seconds(
        SimpleNamespace(
            auth_cache_ttl_seconds=5,
        )
    ) == 45.0

    assert _cache_ttl_seconds(
        SimpleNamespace(
            auth_cache_ttl_seconds=5000,
        )
    ) == 600.0
