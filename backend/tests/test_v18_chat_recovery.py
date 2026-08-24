from __future__ import annotations

from types import SimpleNamespace

import app.services.chat_v7 as chat_v7


def _decision():
    return SimpleNamespace(task_type="general", tier="strong")


def _setup(monkeypatch, *, legacy_ok: bool, telemetry_ok: bool):
    monkeypatch.setattr(
        chat_v7, "base_candidates",
        lambda _d, _p: ["groq", "gemini", "mistral"],
    )
    monkeypatch.setattr(
        chat_v7, "configured_provider", lambda _n, _s: True
    )
    monkeypatch.setattr(
        chat_v7.legacy, "_provider_is_available", lambda _n: legacy_ok
    )
    monkeypatch.setattr(chat_v7, "available", lambda _n: telemetry_ok)
    monkeypatch.setattr(
        chat_v7, "rank_for_task", lambda names, _task: list(names)
    )


def test_shared_cooldown_zero_candidates_enters_recovery(monkeypatch):
    _setup(monkeypatch, legacy_ok=False, telemetry_ok=False)
    settings = SimpleNamespace(
        v18_chat_provider_recovery_enabled=True,
        v18_chat_recovery_max_attempts=5,
    )
    candidates, recovery_mode = chat_v7._select_chat_candidates(
        _decision(), "auto", settings,
        max_attempts=7, excluded_family="",
    )
    assert recovery_mode is True
    assert candidates == ["groq", "mistral", "gemini"]


def test_healthy_routing_stays_primary(monkeypatch):
    _setup(monkeypatch, legacy_ok=True, telemetry_ok=True)
    settings = SimpleNamespace(
        v18_chat_provider_recovery_enabled=True,
        v18_chat_recovery_max_attempts=5,
    )
    candidates, recovery_mode = chat_v7._select_chat_candidates(
        _decision(), "auto", settings,
        max_attempts=7, excluded_family="",
    )
    assert recovery_mode is False
    assert candidates == ["groq", "mistral", "gemini"]


def test_recovery_can_be_disabled(monkeypatch):
    _setup(monkeypatch, legacy_ok=False, telemetry_ok=False)
    settings = SimpleNamespace(
        v18_chat_provider_recovery_enabled=False,
        v18_chat_recovery_max_attempts=5,
    )
    candidates, recovery_mode = chat_v7._select_chat_candidates(
        _decision(), "auto", settings,
        max_attempts=7, excluded_family="",
    )
    assert candidates == []
    assert recovery_mode is False


def test_recovery_respects_excluded_provider_family(monkeypatch):
    monkeypatch.setattr(
        chat_v7, "base_candidates",
        lambda _d, _p: ["groq", "groq_fast", "gemini"],
    )
    monkeypatch.setattr(
        chat_v7, "configured_provider", lambda _n, _s: True
    )
    monkeypatch.setattr(
        chat_v7.legacy, "_provider_is_available", lambda _n: False
    )
    monkeypatch.setattr(chat_v7, "available", lambda _n: False)
    monkeypatch.setattr(
        chat_v7, "rank_for_task", lambda names, _task: list(names)
    )
    settings = SimpleNamespace(
        v18_chat_provider_recovery_enabled=True,
        v18_chat_recovery_max_attempts=5,
    )
    candidates, recovery_mode = chat_v7._select_chat_candidates(
        _decision(), "auto", settings,
        max_attempts=7, excluded_family="groq",
    )
    assert recovery_mode is True
    assert candidates == ["gemini"]
