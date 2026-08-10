from __future__ import annotations

from app.config import Settings
from app.services.image import route_image as route_image_v9
from app.services.omniroute_gateway_v10 import (
    configured as omniroute_configured,
    generate_image as omniroute_generate_image,
)


async def route_image_v10(provider: str, prompt: str, settings: Settings) -> dict:
    # Explicit provider selection remains unchanged.
    if provider != "auto":
        return await route_image_v9(provider, prompt, settings)

    if (
        omniroute_configured(settings)
        and bool(getattr(settings, "omniroute_image_enabled", False))
        and str(getattr(settings, "omniroute_image_model", "") or "").strip()
    ):
        try:
            return await omniroute_generate_image(prompt, settings)
        except Exception:
            # Preserve Vasuki's existing resilient image path as a safe fallback.
            pass

    return await route_image_v9(provider, prompt, settings)
