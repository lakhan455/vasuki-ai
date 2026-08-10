from __future__ import annotations

from app.config import Settings
from app.services.omniroute_gateway_v10 import (
    configured as omniroute_configured,
    embed_texts as omniroute_embed_texts,
)


async def embed_batch_v10(
    texts: list[str],
    settings: Settings,
    *,
    task_type: str,
    title: str | None = None,
    fallback,
) -> list[list[float]]:
    if (
        omniroute_configured(settings)
        and bool(getattr(settings, "omniroute_embedding_enabled", False))
        and str(getattr(settings, "omniroute_embedding_model", "") or "").strip()
    ):
        try:
            return await omniroute_embed_texts(
                texts,
                settings,
                dimensions=int(settings.embedding_dimensions),
            )
        except Exception:
            pass

    return await fallback(
        texts,
        settings,
        task_type=task_type,
        title=title,
    )
