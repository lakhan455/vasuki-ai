from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.personal_memory import list_user_memories
from app.services.project_memory_v8 import list_project_memories
from app.v11.memory import active_memory, normalize_key


_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "your", "you",
    "are", "was", "were", "have", "has", "use", "using", "please",
    "hai", "he", "mera", "meri", "mere", "karna", "karo", "abhi",
    "project", "memory", "remember", "preference", "currently",
}
_TEMPORARY_RE = re.compile(
    r"\b(?:today|tonight|temporary|temporarily|for now|this week|this month|"
    r"abhi|aaj|filhal|haal filhal|in this chat|this conversation)\b",
    re.I,
)
_SESSION_RE = re.compile(
    r"\b(?:for now|for this chat|in this chat|this conversation|today|tonight|"
    r"abhi|aaj|currently|call me|address me|don't use|do not use|nahi use)\b",
    re.I,
)
_NEGATION_RE = re.compile(r"\b(?:not|never|don't|do not|nahi|nhi|mat)\b", re.I)


@dataclass(frozen=True, slots=True)
class MemoryItem:
    scope: str
    key: str
    text: str
    kind: str
    updated_at: datetime
    source: str
    confidence: float = 1.0
    valid_to: datetime | None = None
    raw_id: str = ""

    def public(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "key": self.key,
            "text": self.text,
            "kind": self.kind,
            "updated_at": self.updated_at.isoformat(),
            "source": self.source,
            "confidence": round(float(self.confidence), 3),
            "raw_id": self.raw_id,
        }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dt(value: Any, *, default: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return default or datetime(1970, 1, 1, tzinfo=timezone.utc)
        try:
            result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return default or datetime(1970, 1, 1, tzinfo=timezone.utc)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _tokens(value: str) -> list[str]:
    result: list[str] = []
    for token in re.findall(r"[\w.-]{3,}", str(value or "").casefold()):
        if token in _STOP or token.isdigit():
            continue
        if token not in result:
            result.append(token)
    return result


def _kind(text: str, category: str = "") -> str:
    low = f"{category} {text}".casefold()
    if _TEMPORARY_RE.search(low):
        return "temporary"
    if "goal" in low or "objective" in low:
        return "goal"
    if "decision" in low or any(
        phrase in low
        for phrase in ("must ", "should ", "do not ", "don't ", "keep ")
    ):
        return "decision"
    if "experience" in low or low.startswith(("lesson:", "learned:")):
        return "experience"
    return "preference"


def _render_project_text(row: dict[str, Any]) -> str:
    text = str(row.get("memory_text") or "").strip()
    if not text.startswith("[V71]"):
        return text
    try:
        payload = json.loads(text[len("[V71]"):].strip())
    except Exception:
        return text
    if not isinstance(payload, dict):
        return text
    kind = str(payload.get("kind") or "").casefold()
    if kind == "goal":
        return f"Project goal: {str(payload.get('text') or '').strip()}"
    if kind == "decision":
        title = str(payload.get("title") or "").strip()
        rationale = str(payload.get("rationale") or "").strip()
        return f"Project decision: {title}" + (f" — {rationale}" if rationale else "")
    if kind == "task":
        title = str(payload.get("title") or "").strip()
        status = str(payload.get("status") or "pending").strip()
        priority = str(payload.get("priority") or "normal").strip()
        return f"Project task [{status}/{priority}]: {title}"
    if kind == "last_work":
        summary = str(payload.get("summary") or "").strip()
        next_step = str(payload.get("next_step") or "").strip()
        return f"Project last work: {summary}" + (
            f" — Next: {next_step}" if next_step else ""
        )
    if kind == "repo":
        return f"Project repository: {str(payload.get('label') or '').strip()} {str(payload.get('url') or '').strip()}".strip()
    return text


def _conflict_key(text: str, explicit_key: str = "") -> str:
    if explicit_key.strip():
        return normalize_key(explicit_key)
    low = str(text or "").casefold()
    if re.search(r"\b(?:call me|address me|mujhe .{0,30}(?:bolo|bulana))\b", low):
        return "preferred-address"
    tokens = _tokens(text)
    if not tokens:
        return normalize_key(text)[:120]
    return "|".join(sorted(tokens[:3]))[:180]


def _row_to_personal(row: dict[str, Any]) -> MemoryItem | None:
    text = str(row.get("memory_text") or "").strip()
    if not text:
        return None
    return MemoryItem(
        scope="personal",
        key=_conflict_key(text),
        text=text,
        kind=_kind(text, str(row.get("category") or "")),
        updated_at=_dt(row.get("updated_at") or row.get("created_at")),
        source="user_memories",
        raw_id=str(row.get("id") or ""),
    )


def _row_to_temporal(row: dict[str, Any], project_id: str | None) -> MemoryItem | None:
    value = str(row.get("value") or "").strip()
    key = str(row.get("key") or "").strip()
    if not value:
        return None
    row_project = str(row.get("project_id") or "").strip()
    scope = "project" if project_id and row_project == str(project_id) else "personal"
    if row_project and scope != "project":
        return None
    text = f"{key}: {value}" if key else value
    return MemoryItem(
        scope=scope,
        key=_conflict_key(text, key),
        text=text,
        kind=_kind(text),
        updated_at=_dt(row.get("updated_at") or row.get("valid_from")),
        source=str(row.get("source") or "v11_memory_facts"),
        valid_to=_dt(row.get("valid_to")) if row.get("valid_to") else None,
        raw_id=str(row.get("id") or ""),
    )


def _row_to_project(row: dict[str, Any]) -> MemoryItem | None:
    text = _render_project_text(row)
    if not text:
        return None
    confidence = row.get("confidence")
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 1.0
    return MemoryItem(
        scope="project",
        key=_conflict_key(text),
        text=text,
        kind=_kind(text),
        updated_at=_dt(row.get("updated_at") or row.get("created_at")),
        source=str(row.get("source") or "project_memories"),
        confidence=max(0.0, min(1.0, confidence_value)),
        raw_id=str(row.get("id") or ""),
    )


def session_items(messages: list[dict[str, Any]]) -> list[MemoryItem]:
    now = _utc_now()
    items: list[MemoryItem] = []
    user_messages = [
        str(item.get("content") or "").strip()
        for item in messages
        if str(item.get("role") or "") == "user"
        and str(item.get("content") or "").strip()
    ][-16:]

    for index, content in enumerate(user_messages):
        chunks = [
            re.sub(r"\s+", " ", part).strip()
            for part in re.split(r"(?<=[.!?;])\s+|\n+", content)
        ]
        for chunk in chunks:
            if len(chunk) < 3 or len(chunk) > 500:
                continue
            if not _SESSION_RE.search(chunk):
                continue
            items.append(
                MemoryItem(
                    scope="session",
                    key=_conflict_key(chunk),
                    text=chunk,
                    kind="temporary",
                    updated_at=now + timedelta(microseconds=index),
                    source="current-conversation",
                    raw_id=f"session-{index}-{len(items)}",
                )
            )
    return items[-12:]


def _is_stale(item: MemoryItem, now: datetime) -> bool:
    if item.scope == "session":
        return False
    if item.valid_to is not None and item.valid_to <= now:
        return True
    if item.kind == "temporary":
        age = now - item.updated_at
        return age > timedelta(days=30 if item.scope == "project" else 14)
    return False


def _relevance(query: str, text: str) -> float:
    q = set(_tokens(query))
    t = set(_tokens(text))
    if not q or not t:
        return 0.0
    return len(q & t) / max(1, len(q))


def _conflicts(a: MemoryItem, b: MemoryItem) -> bool:
    if a.key and b.key and a.key == b.key:
        return a.text.casefold() != b.text.casefold()

    ta = set(_tokens(a.text))
    tb = set(_tokens(b.text))
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    if overlap < 0.6:
        return False

    nums_a = set(re.findall(r"\b\d+(?:\.\d+)?\b", a.text))
    nums_b = set(re.findall(r"\b\d+(?:\.\d+)?\b", b.text))
    if nums_a and nums_b and nums_a.isdisjoint(nums_b):
        return True
    return bool(_NEGATION_RE.search(a.text)) != bool(_NEGATION_RE.search(b.text))


def resolve_memory(
    items: list[MemoryItem],
    *,
    query: str = "",
    limit: int = 14,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or _utc_now()
    scope_rank = {"personal": 1, "project": 2, "session": 3}

    stale: list[MemoryItem] = []
    fresh: list[MemoryItem] = []
    seen_text: set[str] = set()
    for item in items:
        normalized = re.sub(r"\s+", " ", item.text).strip().casefold()
        if not normalized or normalized in seen_text:
            continue
        seen_text.add(normalized)
        if _is_stale(item, current):
            stale.append(item)
        else:
            fresh.append(item)

    conflict_order = sorted(
        fresh,
        key=lambda item: (
            scope_rank.get(item.scope, 0),
            item.updated_at.timestamp(),
            item.confidence,
        ),
        reverse=True,
    )

    winners: list[MemoryItem] = []
    suppressed_conflicts: list[MemoryItem] = []
    for candidate in conflict_order:
        if any(_conflicts(chosen, candidate) for chosen in winners):
            suppressed_conflicts.append(candidate)
            continue
        winners.append(candidate)

    def selection_score(item: MemoryItem) -> tuple[float, float]:
        rel = _relevance(query, item.text)
        age_days = max(0.0, (current - item.updated_at).total_seconds() / 86400.0)
        recency = max(0.0, 1.0 - age_days / 365.0)
        kind_boost = 0.12 if item.kind in {"goal", "decision"} else 0.05
        scope_boost = {"personal": 0.03, "project": 0.12, "session": 0.22}.get(item.scope, 0.0)
        return (
            rel * 0.70 + recency * 0.15 + kind_boost + scope_boost,
            item.updated_at.timestamp(),
        )

    winners.sort(key=selection_score, reverse=True)
    selected = winners[: max(1, min(int(limit), 24))]

    return {
        "selected": selected,
        "stale": stale,
        "suppressed_conflicts": suppressed_conflicts,
        "input_count": len(items),
    }


def build_memory_context(resolved: dict[str, Any]) -> str:
    selected = resolved.get("selected") or []
    if not selected:
        return ""

    lines = [
        "VASUKI MEMORY 3.0 — RESOLVED PRIVATE CONTEXT:",
        "Use only when relevant to the user's current request.",
        "Priority on conflict: current conversation > active project > personal memory.",
        "The user's newest explicit statement always overrides older context.",
        "Temporary or expired memory is suppressed at retrieval time; old stored data is not silently deleted.",
        "Never reveal internal memory storage or implementation unless the user asks.",
    ]
    for index, item in enumerate(selected, 1):
        lines.append(
            f"[MEMORY {index} | {item.scope} | {item.kind}] {item.text}"
        )
    return "\n".join(lines)


async def memory3_snapshot(
    settings: Any,
    *,
    user_id: str,
    query: str = "",
    project_id: str | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    personal_task = asyncio.create_task(
        list_user_memories(user_id, settings, limit=60)
    )
    temporal_task = asyncio.create_task(
        active_memory(settings, user_id=user_id, limit=200)
    )
    project_task = (
        asyncio.create_task(
            list_project_memories(
                settings,
                user_id=user_id,
                project_id=project_id,
                limit=120,
            )
        )
        if project_id
        else None
    )

    personal_result, temporal_result = await asyncio.gather(
        personal_task, temporal_task, return_exceptions=True
    )
    project_result: Any = []
    if project_task is not None:
        try:
            project_result = await project_task
        except Exception:
            project_result = []

    items: list[MemoryItem] = []
    if isinstance(personal_result, list):
        for row in personal_result:
            if isinstance(row, dict):
                item = _row_to_personal(row)
                if item:
                    items.append(item)

    if isinstance(temporal_result, list):
        for row in temporal_result:
            if isinstance(row, dict):
                item = _row_to_temporal(row, project_id)
                if item:
                    items.append(item)

    if isinstance(project_result, list):
        for row in project_result:
            if isinstance(row, dict):
                item = _row_to_project(row)
                if item:
                    items.append(item)

    items.extend(session_items(messages or []))
    resolved = resolve_memory(items, query=query)
    context = build_memory_context(resolved)

    selected = resolved["selected"]
    stale = resolved["stale"]
    conflicts = resolved["suppressed_conflicts"]

    return {
        "ok": True,
        "version": "v74",
        "context": context,
        "selected": [item.public() for item in selected],
        "audit": {
            "input_items": resolved["input_count"],
            "selected_items": len(selected),
            "stale_suppressed": len(stale),
            "conflicts_suppressed": len(conflicts),
            "scopes_selected": {
                scope: sum(1 for item in selected if item.scope == scope)
                for scope in ("session", "project", "personal")
            },
        },
    }


def health_snapshot() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v74",
        "name": "Vasuki Memory 3.0",
        "features": [
            "session-memory-from-current-conversation",
            "personal-memory-retrieval",
            "temporal-fact-memory",
            "active-project-memory",
            "scope-priority-resolution",
            "conflict-suppression",
            "temporary-memory-stale-expiry",
            "query-relevance-ranking",
            "memory-audit-snapshot",
            "transparent-chat-context-integration",
        ],
        "scope_priority": ["session", "project", "personal"],
        "write_policy": "existing-explicit-memory-writes-only",
        "silent_persistent_writes": False,
        "destructive_stale_cleanup": False,
        "session_persistence": "current-request/conversation-only",
        "new_database_migration_required": False,
        "new_api_key_required": False,
    }
