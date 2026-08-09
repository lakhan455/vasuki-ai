from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.config import Settings
from app.services import image as legacy
from app.services.image_health_v8 import (
    attempt,
    available,
    failure,
    rank,
    success,
)


@dataclass(frozen=True)
class ImageDecision:
    image_type: str
    requested_edit: bool
    candidates: tuple[str, ...]


def classify_image_request(prompt: str) -> ImageDecision:
    low = str(prompt or "").casefold()
    requested_edit = bool(
        re.search(r"\b(edit|remove|replace|change|retouch|enhance|background|upscale)\b", low)
    )
    if re.search(r"\b(logo|brand mark|emblem|icon)\b", low):
        kind = "logo"
    elif re.search(r"\b(poster|flyer|banner|advertisement|ad creative|social media post)\b", low):
        kind = "poster"
    elif re.search(r"\b(anime|manga|ghibli|cartoon|cel shaded)\b", low):
        kind = "anime"
    elif re.search(r"\b(photo|photoreal|realistic|portrait|cinematic|dslr|camera)\b", low):
        kind = "realistic"
    elif re.search(r"\b(illustration|vector|3d|render|concept art)\b", low):
        kind = "illustration"
    else:
        kind = "general"

    preferred = {
        "realistic": ("huggingface", "cloudflare", "deepai"),
        "anime": ("huggingface", "cloudflare", "deepai"),
        "poster": ("cloudflare", "huggingface", "deepai"),
        "logo": ("cloudflare", "huggingface", "deepai"),
        "illustration": ("cloudflare", "huggingface", "deepai"),
        "general": ("cloudflare", "huggingface", "deepai"),
    }[kind]
    return ImageDecision(kind, requested_edit, preferred)


def enhance_image_prompt(prompt: str, image_type: str) -> str:
    base = re.sub(r"\s+", " ", str(prompt or "")).strip()
    if not base:
        return base

    presets = {
        "realistic": (
            "photorealistic professional photography, natural skin/material texture, "
            "realistic lighting, balanced dynamic range, sharp subject detail, "
            "cinematic composition, physically plausible shadows, clean background"
        ),
        "anime": (
            "high-quality anime illustration, expressive composition, clean line art, "
            "cohesive cel shading, detailed environment, polished character design"
        ),
        "poster": (
            "professional advertising poster, strong visual hierarchy, premium layout, "
            "clear focal point, balanced negative space, brand-ready composition, "
            "print-quality design"
        ),
        "logo": (
            "professional logo concept, simple memorable silhouette, scalable vector-like "
            "geometry, clean negative space, balanced proportions, minimal clutter, "
            "brand-ready presentation"
        ),
        "illustration": (
            "premium digital illustration, deliberate composition, refined shapes, "
            "cohesive lighting, detailed focal subject, production-quality finish"
        ),
        "general": (
            "professional high-detail image, strong composition, coherent lighting, "
            "clean subject separation, polished production-quality finish"
        ),
    }
    suffix = (
        " Avoid accidental text, watermarks, duplicate limbs/objects, malformed geometry, "
        "low-resolution artifacts and clutter unless explicitly requested."
    )
    if len(base) > 1200:
        return base[:1900]
    return f"{base}. {presets.get(image_type, presets['general'])}.{suffix}"[:2048]


def _configured(name: str, settings: Settings) -> bool:
    if name == "cloudflare":
        return bool(settings.cloudflare_account_id and settings.cloudflare_workers_ai)
    if name == "huggingface":
        return bool(settings.hugging_face_inference_api)
    if name == "deepai":
        return bool(settings.deepai_api)
    return False


async def route_image_v8(
    provider: str,
    prompt: str,
    settings: Settings,
    *,
    max_attempts: int = 2,
) -> dict[str, Any]:
    providers: dict[str, Callable[[str, Settings], Awaitable[dict]]] = {
        "cloudflare": legacy.image_cloudflare,
        "huggingface": legacy.image_huggingface,
        "deepai": legacy.image_deepai,
    }
    decision = classify_image_request(prompt)
    enhanced = enhance_image_prompt(prompt, decision.image_type)

    if provider != "auto":
        candidates = [provider] if provider in providers else []
    else:
        candidates = [x for x in decision.candidates if _configured(x, settings) and available(x)]
        candidates = rank(candidates)

    if not candidates:
        candidates = [x for x in decision.candidates if _configured(x, settings)]

    candidates = candidates[: max(1, min(int(max_attempts), 2))]
    if not candidates:
        raise RuntimeError("No image provider is configured.")

    errors: list[str] = []
    for name in candidates:
        started = time.perf_counter()
        attempt(name)
        try:
            result = await asyncio.wait_for(
                providers[name](enhanced, settings),
                timeout=float(settings.image_timeout_seconds) + 15.0,
            )
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            success(name, latency_ms)
            return {
                **result,
                "image_type": decision.image_type,
                "enhanced_prompt": enhanced,
                "original_prompt": prompt,
                "latency_ms": latency_ms,
                "attempted_providers": candidates,
            }
        except Exception as exc:
            failure(name, exc)
            errors.append(f"{name}: {str(exc)[:500]}")
            await asyncio.sleep(0.25)

    raise RuntimeError("Suitable image providers failed. " + " | ".join(errors))
