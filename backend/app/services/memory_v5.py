from __future__ import annotations

import re
from typing import Any

from app.config import Settings
from app.services import personal_memory


_ADDRESS_PATTERNS = (
    re.compile(r"\b(?:mujhe|mere\s+liye)\s+.+?\s+(?:bolo|bulana|bulaya\s+karo)\b", re.I),
    re.compile(r"\bcall\s+me\s+.+", re.I),
    re.compile(r"(?:मुझे|मेरे\s+लिए).+?(?:बोलो|बुलाना|कहकर\s+बुलाना)", re.I),
)

_LANGUAGE_PATTERNS = (
    re.compile(r"\b(?:reply|answer|respond)\s+(?:only\s+)?in\s+\w+", re.I),
    re.compile(r"\b(?:hindi|english|hinglish)\s+me(?:in)?\s+(?:reply|answer|jawab)", re.I),
    re.compile(r"(?:हिंदी|अंग्रेजी|हिंग्लिश)\s+में\s+(?:जवाब|उत्तर)", re.I),
)

_STYLE_PATTERNS = (
    re.compile(r"\b(?:always\s+)?(?:short|concise|brief|detailed)\s+(?:reply|answer)", re.I),
    re.compile(r"\b(?:hamesha\s+)?(?:chhota|short|detail(?:ed)?)\s+(?:jawab|answer)", re.I),
    re.compile(r"(?:हमेशा\s+)?(?:छोटा|संक्षिप्त|विस्तृत)\s+(?:जवाब|उत्तर)", re.I),
)


def memory_slot(value: str) -> str | None:
    cleaned = " ".join(str(value or "").split())
    if not cleaned:
        return None

    if any(pattern.search(cleaned) for pattern in _ADDRESS_PATTERNS):
        return "address_name"
    if any(pattern.search(cleaned) for pattern in _LANGUAGE_PATTERNS):
        return "reply_language"
    if any(pattern.search(cleaned) for pattern in _STYLE_PATTERNS):
        return "answer_style"
    return None


async def remember_with_conflict_resolution(
    user_id: str,
    memory_text: str,
    settings: Settings,
    *,
    category: str = "preference",
    user_jwt: str | None = None,
) -> dict[str, Any]:
    """Save a memory while replacing older contradictory preferences."""

    cleaned = personal_memory.clean_memory_text(memory_text)
    slot = memory_slot(cleaned)

    if slot:
        existing_rows = await personal_memory.list_user_memories(
            user_id,
            settings,
            limit=100,
            user_jwt=user_jwt,
        )
        normalized_new = cleaned.casefold()

        for row in existing_rows:
            old_text = str(row.get("memory_text") or "").strip()
            old_id = str(row.get("id") or "").strip()
            if (
                old_id
                and memory_slot(old_text) == slot
                and old_text.casefold() != normalized_new
            ):
                try:
                    await personal_memory.delete_user_memory(
                        user_id,
                        old_id,
                        settings,
                        user_jwt=user_jwt,
                    )
                except Exception:
                    pass

    return await personal_memory.create_user_memory(
        user_id,
        cleaned,
        settings,
        category=slot or category,
        user_jwt=user_jwt,
    )
