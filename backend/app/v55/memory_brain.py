from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "your", "you",
    "hai", "he", "mera", "meri", "mere", "karna", "karo", "use", "using",
    "project", "preference", "remember", "always", "please",
}


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\w.-]{3,}", str(value or "").casefold())
        if token not in _STOP
    }


def _dt(value: Any) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def memory_kind(row: dict[str, Any]) -> str:
    category = str(row.get("category") or "").casefold()
    text = str(row.get("memory_text") or "").casefold()

    if "goal" in category or re.search(r"\b(?:goal|objective)\b", text):
        return "goal"

    if "experience" in category or text.startswith(("lesson:", "learned:")):
        return "experience"

    if any(
        token in text
        for token in ("must", "should", "keep ", "use ", "do not", "don't")
    ):
        return "decision"

    if any(
        token in text
        for token in ("today", "temporary", "for now", "abhi")
    ):
        return "temporary"

    return "preference"


def _relevance(query: str, text: str) -> float:
    q = _tokens(query)
    t = _tokens(text)
    if not q or not t:
        return 0.0
    return len(q & t) / max(1, len(q))


def _conflicts(newer: dict[str, Any], older: dict[str, Any]) -> bool:
    a = str(newer.get("memory_text") or "")
    b = str(older.get("memory_text") or "")

    ta = _tokens(a)
    tb = _tokens(b)
    shared = ta & tb

    if len(shared) < 2:
        return False

    nums_a = set(re.findall(r"\b\d+(?:\.\d+)?\b", a))
    nums_b = set(re.findall(r"\b\d+(?:\.\d+)?\b", b))

    if nums_a and nums_b and nums_a.isdisjoint(nums_b):
        return True

    neg_a = bool(
        re.search(
            r"\b(?:not|never|don't|do not|nahi|nhi)\b",
            a,
            re.I,
        )
    )
    neg_b = bool(
        re.search(
            r"\b(?:not|never|don't|do not|nahi|nhi)\b",
            b,
            re.I,
        )
    )

    if neg_a != neg_b:
        return True

    return False


def select_memories(
    rows: list[dict[str, Any]],
    *,
    query: str = "",
    limit: int = 12,
) -> tuple[list[dict[str, Any]], int]:
    ordered = sorted(
        (dict(row) for row in rows),
        key=lambda row: _dt(
            row.get("updated_at") or row.get("created_at")
        ),
        reverse=True,
    )

    scored: list[tuple[float, dict[str, Any]]] = []

    for index, row in enumerate(ordered):
        text = str(row.get("memory_text") or "")
        relevance = _relevance(query, text) if query.strip() else 0.0
        recency = max(
            0.0,
            1.0 - index / max(12.0, len(ordered) or 1),
        )
        kind = memory_kind(row)
        kind_boost = 0.12 if kind in {"decision", "goal"} else 0.06
        score = (
            relevance * 0.72
            + recency * 0.18
            + kind_boost
        )
        scored.append((score, row))

    scored.sort(
        key=lambda item: (
            -item[0],
            -_dt(
                item[1].get("updated_at")
                or item[1].get("created_at")
            ).timestamp(),
        )
    )

    selected: list[dict[str, Any]] = []
    superseded = 0

    for _score, row in scored:
        if any(
            memory_kind(row) == memory_kind(chosen)
            and _conflicts(chosen, row)
            for chosen in selected
        ):
            superseded += 1
            continue

        selected.append(row)

        if len(selected) >= max(1, min(int(limit), 20)):
            break

    return selected, superseded


def build_smart_memory_context(
    rows: list[dict[str, Any]],
    *,
    query: str = "",
) -> tuple[str, list[dict[str, Any]]]:
    selected, superseded = select_memories(
        rows,
        query=query,
        limit=12,
    )

    if not selected:
        return "", []

    lines = [
        "PRIVATE USER MEMORY — V55 SMART SELECTION:",
        "Use only when relevant to the current user request.",
        (
            "When memories conflict, the newest explicit user instruction wins; "
            "never merge contradictory preferences."
        ),
        (
            "Do not reveal database/internal memory implementation unless "
            "the user asks."
        ),
    ]

    if superseded:
        lines.append(
            (
                f"{superseded} older conflicting memory item(s) were "
                "suppressed for this turn."
            )
        )

    for index, row in enumerate(selected, 1):
        kind = memory_kind(row)
        lines.append(
            (
                f"[USER MEMORY {index} | {kind}] "
                f"{str(row.get('memory_text') or '').strip()}"
            )
        )

    return "\n".join(lines), selected


def health_snapshot() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v55",
        "name": "Vasuki Memory + Project Context Brain",
        "features": [
            "query-relevant-personal-memory",
            "newest-memory-wins-on-conflict",
            "retrieval-time-outdated-memory-suppression",
            "memory-type-classification",
            "active-project-context",
            "project-code-context-on-coding-intent",
        ],
        "destructive_memory_cleanup": False,
        "new_database_migration_required": False,
    }
