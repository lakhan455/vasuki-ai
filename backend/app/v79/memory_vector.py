from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import quote

import httpx

from app.services.personal_memory import list_user_memories
from app.services.rag import embed_query


def _base_url(settings: Any) -> str:
    return str(
        getattr(settings, "supabase_url", "")
        or ""
    ).rstrip("/")


def _server_key(settings: Any) -> str:
    return str(
        getattr(
            settings,
            "supabase_secret_key",
            None,
        )
        or getattr(
            settings,
            "supabase_service_role_key",
            None,
        )
        or ""
    )


def _headers(settings: Any) -> dict[str, str]:
    key = _server_key(settings)

    headers = {
        "apikey": key,
        "Content-Type": "application/json",
    }

    if key and not key.startswith("sb_secret_"):
        headers["Authorization"] = (
            f"Bearer {key}"
        )

    return headers


def configured(settings: Any) -> bool:
    return bool(
        getattr(
            settings,
            "v79_memory_vector_enabled",
            True,
        )
        and _base_url(settings)
        and _server_key(settings)
        and getattr(
            settings,
            "google_gemini_api",
            None,
        )
    )


def short_term_window(
    messages: list[dict[str, Any]] | None,
    *,
    limit: int = 10,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    source = list(
        messages or []
    )

    for item in source[
        -max(
            1,
            min(
                int(limit),
                20,
            ),
        ):
    ]:
        role = str(
            item.get("role")
            or ""
        ).strip().casefold()

        content = re.sub(
            r"\s+",
            " ",
            str(
                item.get("content")
                or ""
            ),
        ).strip()

        if role not in {
            "user",
            "assistant",
            "system",
        }:
            continue

        if not content:
            continue

        rows.append(
            {
                "role": role,
                "content": content[:3000],
            }
        )

    return rows


def _tokens(
    value: str,
) -> set[str]:
    return set(
        re.findall(
            r"[\w.-]{3,}",
            str(
                value or ""
            ).casefold(),
        )
    )


def _lexical_score(
    query: str,
    text: str,
) -> float:
    query_tokens = _tokens(query)
    text_tokens = _tokens(text)

    if (
        not query_tokens
        or not text_tokens
    ):
        return 0.0

    return (
        len(
            query_tokens
            & text_tokens
        )
        / max(
            1,
            len(query_tokens),
        )
    )


async def _vector_rows(
    settings: Any,
    *,
    user_id: str,
) -> list[dict[str, Any]]:
    if (
        not _base_url(settings)
        or not _server_key(settings)
    ):
        return []

    url = (
        f"{_base_url(settings)}"
        "/rest/v1/user_memories"
        f"?user_id=eq.{quote(user_id)}"
        "&select="
        "id,memory_text,category,"
        "created_at,updated_at,embedding"
        "&order=updated_at.desc"
        "&limit=100"
    )

    try:
        async with httpx.AsyncClient(
            timeout=8.0
        ) as client:
            response = await client.get(
                url,
                headers=_headers(settings),
            )

        response.raise_for_status()

        rows = response.json()

        if isinstance(
            rows,
            list,
        ):
            return rows

    except Exception:
        pass

    return []


async def _backfill_embeddings(
    settings: Any,
    *,
    user_id: str,
    rows: list[dict[str, Any]],
    max_items: int = 8,
) -> int:
    if not configured(settings):
        return 0

    candidates = []

    for row in rows:
        if len(
            candidates
        ) >= max(
            0,
            min(
                int(max_items),
                12,
            ),
        ):
            break

        memory_id = str(
            row.get("id")
            or ""
        ).strip()

        text = str(
            row.get("memory_text")
            or ""
        ).strip()

        embedding = row.get(
            "embedding"
        )

        if (
            not memory_id
            or not text
            or embedding
        ):
            continue

        candidates.append(
            (
                memory_id,
                text,
            )
        )

    updated = 0

    for (
        memory_id,
        text,
    ) in candidates:
        try:
            vector = await embed_query(
                text[:12000],
                settings,
            )

            url = (
                f"{_base_url(settings)}"
                "/rest/v1/user_memories"
                f"?id=eq.{quote(memory_id)}"
                f"&user_id=eq.{quote(user_id)}"
            )

            async with httpx.AsyncClient(
                timeout=8.0
            ) as client:
                response = await client.patch(
                    url,
                    headers=_headers(
                        settings
                    ),
                    json={
                        "embedding": vector
                    },
                )

            if not response.is_error:
                updated += 1

        except Exception:
            continue

    return updated


async def _semantic_rpc(
    settings: Any,
    *,
    user_id: str,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    vector = await embed_query(
        str(query)[:12000],
        settings,
    )

    url = (
        f"{_base_url(settings)}"
        "/rest/v1/rpc/"
        "match_user_memories_v79"
    )

    payload = {
        "p_user_id": user_id,
        "p_query_embedding": vector,
        "p_match_count": max(
            1,
            min(
                int(limit),
                20,
            ),
        ),
    }

    async with httpx.AsyncClient(
        timeout=10.0
    ) as client:
        response = await client.post(
            url,
            headers=_headers(settings),
            json=payload,
        )

    response.raise_for_status()

    rows = response.json()

    if isinstance(
        rows,
        list,
    ):
        return rows

    return []


async def semantic_memories(
    settings: Any,
    *,
    user_id: str,
    query: str,
    limit: int = 8,
) -> dict[str, Any]:
    safe_limit = max(
        1,
        min(
            int(limit),
            20,
        ),
    )

    fallback_rows = await (
        list_user_memories(
            user_id,
            settings,
            limit=60,
        )
    )

    lexical_rows = sorted(
        fallback_rows,
        key=lambda row: (
            _lexical_score(
                query,
                str(
                    row.get(
                        "memory_text"
                    )
                    or ""
                ),
            )
        ),
        reverse=True,
    )

    if (
        not configured(settings)
        or not str(
            query or ""
        ).strip()
    ):
        return {
            "mode": "lexical-fallback",
            "items": lexical_rows[
                :safe_limit
            ],
            "backfilled": 0,
        }

    vector_rows = await _vector_rows(
        settings,
        user_id=user_id,
    )

    if not vector_rows:
        return {
            "mode": "lexical-fallback",
            "items": lexical_rows[
                :safe_limit
            ],
            "backfilled": 0,
        }

    backfill_task = (
        asyncio.create_task(
            _backfill_embeddings(
                settings,
                user_id=user_id,
                rows=vector_rows,
                max_items=8,
            )
        )
    )

    try:
        semantic_rows = (
            await _semantic_rpc(
                settings,
                user_id=user_id,
                query=query,
                limit=safe_limit,
            )
        )

        backfilled = (
            await backfill_task
        )

        semantic_rows = _clean_semantic_rows(
            semantic_rows
        )

        if semantic_rows:
            return {
                "mode": "vector",
                "items": (
                    semantic_rows[
                        :safe_limit
                    ]
                ),
                "backfilled": (
                    backfilled
                ),
            }

        if backfilled:
            semantic_rows = (
                await _semantic_rpc(
                    settings,
                    user_id=user_id,
                    query=query,
                    limit=safe_limit,
                )
            )

            semantic_rows = _clean_semantic_rows(
                semantic_rows
            )

            if semantic_rows:
                return {
                    "mode": "vector",
                    "items": (
                        semantic_rows[
                            :safe_limit
                        ]
                    ),
                    "backfilled": (
                        backfilled
                    ),
                }

    except Exception:
        if not backfill_task.done():
            backfill_task.cancel()

    return {
        "mode": "lexical-fallback",
        "items": lexical_rows[
            :safe_limit
        ],
        "backfilled": 0,
    }


def build_memory_context(
    items: list[dict[str, Any]],
) -> str:
    if not items:
        return ""

    cleaned: list[str] = []
    seen: set[str] = set()

    for row in items:
        text = re.sub(
            r"\s+",
            " ",
            str(
                row.get(
                    "memory_text"
                )
                or ""
            ),
        ).strip()

        key = text.casefold()

        if (
            not text
            or key in seen
        ):
            continue

        seen.add(key)
        cleaned.append(
            text[:600]
        )

    if not cleaned:
        return ""

    lines = [
        (
            "VASUKI V79 SEMANTIC "
            "LONG-TERM MEMORY:"
        ),
        (
            "Use only when relevant. "
            "The user's newest explicit "
            "statement overrides older memory."
        ),
    ]

    for (
        index,
        text,
    ) in enumerate(
        cleaned,
        1,
    ):
        lines.append(
            f"[LONG-TERM {index}] "
            f"{text}"
        )

    return "\n".join(lines)


async def memory79_snapshot(
    settings: Any,
    *,
    user_id: str,
    query: str,
    messages: list[dict[str, Any]]
    | None = None,
) -> dict[str, Any]:
    long_term_limit = int(
        getattr(
            settings,
            "v79_vector_match_count",
            8,
        )
        or 8
    )

    short_term_limit = int(
        getattr(
            settings,
            "v79_short_term_messages",
            10,
        )
        or 10
    )

    semantic = await (
        semantic_memories(
            settings,
            user_id=user_id,
            query=query,
            limit=long_term_limit,
        )
    )

    recent = short_term_window(
        messages,
        limit=short_term_limit,
    )

    return {
        "ok": True,
        "version": "v79",
        "retrieval_mode": (
            semantic["mode"]
        ),
        "context": (
            build_memory_context(
                semantic["items"]
            )
        ),
        "short_term": recent,
        "long_term": (
            semantic["items"]
        ),
        "backfilled": (
            semantic["backfilled"]
        ),
    }


def health_snapshot(
    settings: Any,
) -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v79",
        "name": (
            "Vasuki Semantic Memory"
        ),
        "vector_enabled": bool(
            getattr(
                settings,
                "v79_memory_vector_enabled",
                True,
            )
        ),
        "vector_runtime_configured": (
            configured(settings)
        ),
        "short_term_messages": int(
            getattr(
                settings,
                "v79_short_term_messages",
                10,
            )
            or 10
        ),
        "vector_match_count": int(
            getattr(
                settings,
                "v79_vector_match_count",
                8,
            )
            or 8
        ),
        "storage": (
            "Supabase PostgreSQL + pgvector"
        ),
        "fallback": (
            "existing lexical memory retrieval"
        ),
        "migration": (
            "supabase/v79_memory_vectors.sql"
        ),
        "existing_v74_preserved": True,
    }

def novel_memory_context(
    base_context: str,
    items: list[dict[str, Any]],
) -> str:
    """
    Build V79 semantic context while skipping memories
    already present in the existing V74/base context.
    """

    normalized_base = re.sub(
        r"\s+",
        " ",
        str(base_context or ""),
    ).strip().casefold()

    novel: list[dict[str, Any]] = []

    for row in items:
        text = re.sub(
            r"\s+",
            " ",
            str(row.get("memory_text") or ""),
        ).strip()

        if not text:
            continue

        normalized = text.casefold()

        if normalized and normalized in normalized_base:
            continue

        novel.append(row)

    return build_memory_context(novel)

def _clean_semantic_rows(
    rows: list[dict[str, Any]],
    *,
    min_similarity: float = 0.55,
) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in rows:
        text = re.sub(
            r"\s+",
            " ",
            str(row.get("memory_text") or ""),
        ).strip()

        try:
            similarity = float(row.get("similarity") or 0.0)
        except (TypeError, ValueError):
            similarity = 0.0

        # Ignore low-confidence semantic matches.
        if similarity < min_similarity:
            continue

        # Ignore old mojibake/corrupted UTF-8 memories.
        if "Ã Â¤" in text or "Ãƒ" in text:
            continue

        key = text.casefold()

        if not text or key in seen:
            continue

        seen.add(key)
        cleaned.append(row)

    return cleaned
