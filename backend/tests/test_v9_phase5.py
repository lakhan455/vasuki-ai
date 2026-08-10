from __future__ import annotations

import pytest

from app.main_v9_phase5 import app
from app.services.account_v9 import _sanitize, validate_delete_confirmation
from app.services.push_v9 import _endpoint_hash
from app.services.storage_v9 import DEFAULT_STORAGE_QUOTAS, StorageQuotaExceeded


def test_phase5_export_sanitizer_removes_sensitive_derived_fields():
    value = _sanitize({
        "content": "hello",
        "embedding": [1, 2, 3],
        "nested": {"signature": "secret", "safe": True},
    })
    assert value == {"content": "hello", "nested": {"safe": True}}


def test_phase5_delete_confirmation_requires_exact_phrase_and_email():
    validate_delete_confirmation(
        account_email="user@example.com",
        confirm_email="USER@example.com",
        confirmation="DELETE MY ACCOUNT",
    )
    with pytest.raises(ValueError):
        validate_delete_confirmation(
            account_email="user@example.com",
            confirm_email="user@example.com",
            confirmation="delete my account",
        )


def test_phase5_push_endpoint_hash_stable():
    first = _endpoint_hash("https://push.example.test/sub/1")
    second = _endpoint_hash("https://push.example.test/sub/1")
    assert first == second
    assert len(first) == 64


def test_phase5_storage_quotas_are_ordered():
    assert DEFAULT_STORAGE_QUOTAS["free"] < DEFAULT_STORAGE_QUOTAS["pro"]
    assert DEFAULT_STORAGE_QUOTAS["pro"] < DEFAULT_STORAGE_QUOTAS["owner"]


def test_phase5_quota_exception_is_user_input_error():
    assert issubclass(StorageQuotaExceeded, ValueError)


def test_phase5_routes_registered():
    paths = {path for route in app.routes if (path := getattr(route, "path", None))}
    expected = {
        "/api/account/v9/chats",
        "/api/account/v9/export/chat/{chat_id}",
        "/api/account/v9/export/full",
        "/api/account/v9",
        "/api/storage/v9",
        "/api/storage/v9/cleanup",
        "/api/push/v9/config",
        "/api/push/v9/subscribe",
        "/health/v9-phase5",
    }
    assert expected.issubset(paths)
