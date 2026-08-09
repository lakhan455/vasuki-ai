from __future__ import annotations

import re
from typing import Any

from app.services.context import ContextStats
from app.services.context_v7 import compact_messages_v7


_IMPORTANT = re.compile(
    r"(?i)\b(project|repo|github|render|vercel|supabase|path|folder|file|"
    r"version|v\d+|commit|deploy|decid|require|must|should|want|need|"
    r"pending|next|todo|issue|error|fail|fix|url|api|model|provider|"
    r"limit|quota|memory|document|image|router)\b"
)


def _clean(value: str, limit: int = 360) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return value[:limit].rstrip()


def _project_digest(messages: list[dict[str, Any]], max_items: int = 18) -> str:
    candidates: list[str] = []
    seen: set[str] = set()

    for item in messages:
        role = str(item.get("role") or "")
        content = str(item.get("content") or "")
        if not content:
            continue
        for part in re.split(r"(?<=[.!?])\s+|\n+", content):
            text = _clean(part)
            if len(text) < 12 or not _IMPORTANT.search(text):
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            candidates.append(f"- {role}: {text}")

    return "\n".join(candidates[-max_items:])


def compact_messages_v8(
    messages: list[dict[str, Any]],
    *,
    max_chars: int,
    max_single_message_chars: int,
):
    if len(messages) <= 10:
        return compact_messages_v7(
            messages,
            max_chars=max_chars,
            max_single_message_chars=max_single_message_chars,
        )

    latest = messages[-8:]
    older = messages[:-8]
    digest = _project_digest(older)

    synthetic: list[dict[str, Any]] = []
    if digest:
        synthetic.append(
            {
                "role": "system",
                "content": (
                    "CONVERSATION STATE DIGEST (extractive; do not invent facts):\n"
                    "Preserve project state, decisions, constraints, unresolved tasks, "
                    "paths/versions and errors when relevant.\n"
                    + digest
                ),
            }
        )
    synthetic.extend(latest)

    compacted, stats = compact_messages_v7(
        synthetic,
        max_chars=max_chars,
        max_single_message_chars=max_single_message_chars,
    )
    return compacted, ContextStats(
        original_chars=sum(len(str(x.get("content") or "")) for x in messages),
        used_chars=sum(len(str(x.get("content") or "")) for x in compacted),
        omitted_messages=max(1, len(older)),
        truncated_messages=stats.truncated_messages,
    )
