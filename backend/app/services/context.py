from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextStats:
    original_chars: int
    used_chars: int
    omitted_messages: int
    truncated_messages: int

    @property
    def trimmed(self) -> bool:
        return self.omitted_messages > 0 or self.truncated_messages > 0


def _message_cost(message: dict) -> int:
    return len(str(message.get("content") or "")) + len(str(message.get("role") or "")) + 12


def _truncate_text(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False

    marker = (
        "\n\n[... middle of this very large message was automatically omitted "
        "to keep the conversation within the model context ...]\n\n"
    )

    if limit <= len(marker) + 200:
        return text[:limit], True

    available = limit - len(marker)
    head_size = int(available * 0.65)
    tail_size = available - head_size
    return text[:head_size] + marker + text[-tail_size:], True


def compact_messages(
    messages: list[dict],
    *,
    max_chars: int,
    max_single_message_chars: int,
) -> tuple[list[dict], ContextStats]:
    """Keep the newest useful turns instead of rejecting a long conversation.

    The latest turns are selected backwards until the budget is full. Oversized
    individual messages retain their beginning and end, which is useful for
    code because imports/configuration are often at the top and errors/output
    are often at the bottom.
    """
    clean: list[dict] = []
    original_chars = 0
    truncated_messages = 0

    for item in messages:
        role = str(item.get("role") or "user")
        content = str(item.get("content") or "")
        original_chars += len(content)

        truncated, changed = _truncate_text(content, max_single_message_chars)
        if changed:
            truncated_messages += 1

        clean.append({"role": role, "content": truncated})

    if not clean:
        return [], ContextStats(0, 0, 0, 0)

    # Reserve a small amount for a context-compaction notice.
    selection_budget = max(4000, max_chars - 700)
    selected_reversed: list[dict] = []
    used = 0
    omitted_messages = 0

    for item in reversed(clean):
        cost = _message_cost(item)

        # Always retain the newest message, even if it needs one more truncation.
        if not selected_reversed:
            if cost > selection_budget:
                shortened, changed = _truncate_text(
                    item["content"],
                    max(2000, selection_budget - 50),
                )
                if changed:
                    truncated_messages += 1
                item = {"role": item["role"], "content": shortened}
                cost = _message_cost(item)

            selected_reversed.append(item)
            used += cost
            continue

        if used + cost <= selection_budget:
            selected_reversed.append(item)
            used += cost
        else:
            omitted_messages += 1

    selected = list(reversed(selected_reversed))

    if omitted_messages or truncated_messages:
        notice = {
            "role": "system",
            "content": (
                "SMART CONTEXT NOTICE: Some older conversation content was "
                "automatically compacted because the chat became very long. "
                "Prioritize the newest user request and the retained recent "
                "messages. Do not claim that omitted text was visible."
            ),
        }

        while selected and used + _message_cost(notice) > max_chars and len(selected) > 1:
            removed = selected.pop(0)
            used -= _message_cost(removed)
            omitted_messages += 1

        selected.insert(0, notice)
        used += _message_cost(notice)

    stats = ContextStats(
        original_chars=original_chars,
        used_chars=sum(len(item["content"]) for item in selected),
        omitted_messages=omitted_messages,
        truncated_messages=truncated_messages,
    )
    return selected, stats
