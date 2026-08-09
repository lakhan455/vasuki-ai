from __future__ import annotations

import re
from typing import Any

from app.config import Settings
from app.services.project_memory_v8 import add_project_memory

_PROJECT_SIGNALS = (
    "project", "workspace", "theme", "color", "colour", "stack", "framework",
    "database", "supabase", "backend", "frontend", "domain", "url", "path",
    "folder", "deploy", "render", "vercel", "requirement", "feature", "api",
    "model", "deadline", "must", "should", "prefer", "preferred", "use ",
    "keep ", "always ", "cahiye", "chahiye", "rhega", "rahega", "isme",
    "banana", "banani", "banega", "karna hai", "karna he",
)

_QUESTION_PREFIXES = (
    "what ", "why ", "how ", "when ", "where ", "who ", "which ",
    "kya ", "kaise ", "kese ", "kab ", "kaha ", "kaun ",
)

_TRANSIENT_ONLY = (
    "hello", "hi", "thanks", "thank you", "ok", "okay", "done", "test",
)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def extract_project_memory_candidates(
    messages: list[dict[str, Any]],
    *,
    max_candidates: int = 4,
) -> list[str]:
    """High-precision, zero-LLM extraction of explicit project facts/instructions."""
    candidates: list[str] = []
    seen: set[str] = set()

    for message in reversed(messages[-24:]):
        if str(message.get("role") or "").casefold() != "user":
            continue

        content = _clean(str(message.get("content") or ""))
        if not content:
            continue

        segments = re.split(r"(?<=[.!])\s+|\n+|;\s*", content)
        for segment in segments:
            text = _clean(segment)
            low = text.casefold()

            if len(text) < 12 or len(text) > 420:
                continue
            if low in _TRANSIENT_ONLY:
                continue
            if text.endswith("?") or any(low.startswith(prefix) for prefix in _QUESTION_PREFIXES):
                continue
            if not any(signal in low for signal in _PROJECT_SIGNALS):
                continue

            normalized = low.strip(" .,:;-")
            if normalized in seen:
                continue

            seen.add(normalized)
            candidates.append(text)
            if len(candidates) >= max(1, min(max_candidates, 6)):
                return candidates

    return candidates


async def auto_capture_project_memories(
    settings: Settings,
    *,
    user_id: str,
    project_id: str,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    candidates = extract_project_memory_candidates(messages)
    saved: list[dict[str, Any]] = []
    errors: list[str] = []

    for candidate in candidates:
        try:
            item = await add_project_memory(
                settings,
                user_id=user_id,
                project_id=project_id,
                memory_text=candidate,
                source="auto-chat",
                confidence=0.90,
            )
            saved.append(item)
        except ValueError:
            continue
        except Exception as exc:
            errors.append(type(exc).__name__)

    return {
        "ok": True,
        "candidates": len(candidates),
        "saved": saved,
        "saved_count": len(saved),
        "errors": errors[:3],
    }
