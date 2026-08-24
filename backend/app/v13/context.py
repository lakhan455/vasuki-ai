from __future__ import annotations

from typing import Any


def _clip_tail(item: dict[str, Any], allowance: int, marker: str) -> dict[str, Any] | None:
    if allowance <= 0:
        return None

    text = str(item.get("content") or "")
    if len(text) <= allowance:
        return {**item, "content": text}

    if allowance <= len(marker):
        clipped = text[-allowance:]
    else:
        clipped = marker + text[-(allowance - len(marker)):]

    return {**item, "content": clipped}


def compress_messages(
    messages: list[dict[str, Any]],
    *,
    max_chars: int = 45000,
    preserve_last: int = 12,
) -> list[dict[str, Any]]:
    rows = [
        {**item, "content": str(item.get("content") or "")}
        for item in messages
    ]
    if not rows:
        return []

    max_chars = max(1, int(max_chars))
    total = sum(len(item["content"]) for item in rows)
    if total <= max_chars:
        return rows

    preserve_last = max(1, min(int(preserve_last), len(rows)))
    recent_source = rows[-preserve_last:]
    older = rows[:-preserve_last]

    remaining = max_chars
    recent_reversed: list[dict[str, Any]] = []

    for index, item in enumerate(reversed(recent_source)):
        if remaining <= 0:
            break

        text = item["content"]
        allowance = min(len(text), remaining)
        marker = (
            "[Latest context clipped]\n"
            if index == 0
            else "[Recent context clipped]\n"
        )

        clipped = _clip_tail(item, allowance, marker)
        if clipped is None:
            break

        recent_reversed.append(clipped)
        remaining -= len(clipped["content"])

    recent = list(reversed(recent_reversed))

    compacted_reversed: list[dict[str, Any]] = []
    for item in reversed(older):
        if remaining <= 0:
            break

        allowance = min(len(item["content"]), remaining)
        clipped = _clip_tail(item, allowance, "[Earlier context clipped]\n")
        if clipped is None:
            break

        compacted_reversed.append(clipped)
        remaining -= len(clipped["content"])

    compacted = list(reversed(compacted_reversed))
    result = [*compacted, *recent]

    used = sum(len(item["content"]) for item in result)
    if used > max_chars:
        overflow = used - max_chars
        for item in result:
            if overflow <= 0:
                break
            text = item["content"]
            if len(text) <= overflow:
                overflow -= len(text)
                item["content"] = ""
            else:
                item["content"] = text[overflow:]
                overflow = 0
        result = [item for item in result if item["content"]]

    return result
