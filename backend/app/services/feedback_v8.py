from __future__ import annotations

import uuid
from typing import Any

import httpx

from app.config import Settings
from app.services.analytics_v8 import _base, _headers, configured
from app.services.quality_v9 import observe_feedback

VALID_CATEGORIES = {
    'incorrect', 'slow', 'outdated', 'bad_code', 'bad_image',
    'good', 'helpful', 'other'
}


def normalize_feedback_category(value: str) -> str:
    clean = str(value or 'other').strip().lower().replace(' ', '_')
    return clean if clean in VALID_CATEGORIES else 'other'


async def save_feedback(
    settings: Settings,
    *,
    user_id: str,
    rating: str,
    category: str,
    message_id: str | None = None,
    comment: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not configured(settings):
        raise RuntimeError('Supabase is not configured.')
    payload = {
        'id': str(uuid.uuid4()),
        'user_id': user_id,
        'rating': 'down' if str(rating).lower().startswith('d') else 'up',
        'category': normalize_feedback_category(category),
        'message_id': str(message_id or '')[:120] or None,
        'comment': str(comment or '')[:3000] or None,
        'metadata': metadata or {},
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{_base(settings)}/rest/v1/response_feedback",
            headers=_headers(settings, representation=True),
            json=payload,
        )
    response.raise_for_status()
    meta = metadata or {}
    observe_feedback(
        str(meta.get("provider") or ""),
        payload["rating"],
        task_type=str(meta.get("task_type") or "") or None,
        category=payload["category"],
    )
    rows = response.json()
    if isinstance(rows, list) and rows:
        return rows[0]
    return payload
