from __future__ import annotations

import asyncio
import base64
import re
from io import BytesIO
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from app.config import Settings
from app.services.image_v8 import route_image_v8
from app.services.vision import process_vision_request


IMAGE_PRESETS: dict[str, str] = {
    "none": "",
    "photo": "natural professional photography, realistic texture, balanced exposure, camera-authentic detail",
    "cinematic": "cinematic lighting, controlled contrast, dramatic depth, premium film still composition",
    "product": "premium commercial product photography, clean studio lighting, crisp edges, catalogue-ready composition",
    "poster": "professional advertising poster composition, strong hierarchy, clear focal point, intentional negative space",
    "logo": "minimal brand mark concept, simple memorable silhouette, vector-like geometry, clean negative space",
    "anime": "high-quality anime illustration, clean line art, cohesive cel shading, polished character design",
    "3d": "premium 3D render, physically plausible materials, studio-grade lighting, refined geometry",
}

ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "square": (1024, 1024),
    "portrait": (1024, 1280),
    "landscape": (1280, 720),
    "story": (720, 1280),
    "classic": (1200, 900),
}

_PRESET_ALIASES = {
    "realistic": "photo",
    "photorealistic": "photo",
    "film": "cinematic",
    "ad": "poster",
    "advertisement": "poster",
    "illustration": "3d",
}

_RATIO_ALIASES = {
    "1:1": "square",
    "4:5": "portrait",
    "16:9": "landscape",
    "9:16": "story",
    "4:3": "classic",
}


def normalize_preset(value: str | None) -> str:
    key = str(value or "none").strip().casefold()
    key = _PRESET_ALIASES.get(key, key)
    return key if key in IMAGE_PRESETS else "none"


def normalize_aspect_ratio(value: str | None) -> str:
    key = str(value or "square").strip().casefold()
    key = _RATIO_ALIASES.get(key, key)
    return key if key in ASPECT_RATIOS else "square"


def studio_prompt(
    prompt: str,
    *,
    preset: str = "none",
    aspect_ratio: str = "square",
    variation_index: int = 0,
) -> str:
    clean = re.sub(r"\s+", " ", str(prompt or "")).strip()
    if not clean:
        raise ValueError("Image prompt is required.")
    preset_key = normalize_preset(preset)
    ratio_key = normalize_aspect_ratio(aspect_ratio)
    width, height = ASPECT_RATIOS[ratio_key]
    ratio_hint = f"compose for {width}:{height} ({ratio_key}) framing"
    parts = [clean, ratio_hint]
    if IMAGE_PRESETS[preset_key]:
        parts.append(IMAGE_PRESETS[preset_key])
    if variation_index > 0:
        parts.append(
            f"variation {variation_index}: keep the same core brief while changing composition, camera angle or layout meaningfully"
        )
    return ". ".join(parts)[:1900]


def _decode_data_url(data_url: str) -> tuple[bytes, str]:
    match = re.match(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$", str(data_url or ""), re.S)
    if not match:
        raise ValueError("Expected an image data URL.")
    return base64.b64decode(match.group(2)), match.group(1).casefold()


def _png_data_url(content: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(content).decode("ascii")


def _fit_image(image: Image.Image, width: int, height: int) -> Image.Image:
    source = ImageOps.exif_transpose(image).convert("RGB")
    fitted = ImageOps.fit(
        source,
        (width, height),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    return fitted


def fit_data_url_to_ratio(data_url: str, aspect_ratio: str) -> tuple[str, dict[str, Any]]:
    ratio_key = normalize_aspect_ratio(aspect_ratio)
    width, height = ASPECT_RATIOS[ratio_key]
    raw, _mime = _decode_data_url(data_url)
    with Image.open(BytesIO(raw)) as image:
        fitted = _fit_image(image, width, height)
        buffer = BytesIO()
        fitted.save(buffer, format="PNG", optimize=True)
    return _png_data_url(buffer.getvalue()), {
        "aspect_ratio": ratio_key,
        "width": width,
        "height": height,
        "aspect_applied": True,
    }


def upscale_image_bytes(
    content: bytes,
    *,
    scale: float = 2.0,
    max_long_edge: int = 4096,
) -> tuple[bytes, dict[str, Any]]:
    safe_scale = max(1.0, min(float(scale), 4.0))
    with Image.open(BytesIO(content)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        original_width, original_height = image.size
        desired_width = max(1, round(original_width * safe_scale))
        desired_height = max(1, round(original_height * safe_scale))
        longest = max(desired_width, desired_height)
        if longest > max_long_edge:
            shrink = max_long_edge / longest
            desired_width = max(1, round(desired_width * shrink))
            desired_height = max(1, round(desired_height * shrink))
        enlarged = image.resize(
            (desired_width, desired_height),
            Image.Resampling.LANCZOS,
        )
        enlarged = ImageEnhance.Sharpness(enlarged).enhance(1.18)
        enlarged = ImageEnhance.Contrast(enlarged).enhance(1.03)
        enlarged = enlarged.filter(ImageFilter.UnsharpMask(radius=1.1, percent=85, threshold=3))
        buffer = BytesIO()
        enlarged.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), {
        "original_width": original_width,
        "original_height": original_height,
        "width": desired_width,
        "height": desired_height,
        "requested_scale": safe_scale,
        "method": "lanczos+local-enhancement",
        "generative_super_resolution": False,
    }


async def generate_studio_image(
    settings: Settings,
    *,
    prompt: str,
    preset: str = "none",
    aspect_ratio: str = "square",
    variation_index: int = 0,
) -> dict[str, Any]:
    preset_key = normalize_preset(preset)
    ratio_key = normalize_aspect_ratio(aspect_ratio)
    routed_prompt = studio_prompt(
        prompt,
        preset=preset_key,
        aspect_ratio=ratio_key,
        variation_index=variation_index,
    )
    result = await route_image_v8(
        "auto",
        routed_prompt,
        settings,
        max_attempts=2,
    )
    url = str(result.get("url") or "")
    aspect_meta: dict[str, Any] = {
        "aspect_ratio": ratio_key,
        "width": ASPECT_RATIOS[ratio_key][0],
        "height": ASPECT_RATIOS[ratio_key][1],
        "aspect_applied": False,
    }
    if url.startswith("data:image/"):
        try:
            url, aspect_meta = fit_data_url_to_ratio(url, ratio_key)
        except Exception:
            pass
    return {
        **result,
        "url": url,
        "preset": preset_key,
        "studio_prompt": routed_prompt,
        **aspect_meta,
    }


async def generate_variations(
    settings: Settings,
    *,
    prompt: str,
    preset: str,
    aspect_ratio: str,
    count: int,
) -> dict[str, Any]:
    safe_count = max(2, min(int(count), 4))
    semaphore = asyncio.Semaphore(2)

    async def one(index: int) -> dict[str, Any]:
        async with semaphore:
            try:
                value = await generate_studio_image(
                    settings,
                    prompt=prompt,
                    preset=preset,
                    aspect_ratio=aspect_ratio,
                    variation_index=index,
                )
                return {"ok": True, "index": index, **value}
            except Exception as exc:
                return {"ok": False, "index": index, "error": str(exc)[:800]}

    rows = await asyncio.gather(*(one(index) for index in range(1, safe_count + 1)))
    return {
        "items": rows,
        "requested": safe_count,
        "succeeded": sum(1 for item in rows if item.get("ok")),
        "failed": sum(1 for item in rows if not item.get("ok")),
    }


async def edit_studio_image(
    settings: Settings,
    *,
    content: bytes,
    filename: str,
    mime_type: str,
    prompt: str,
    preset: str = "none",
    aspect_ratio: str = "square",
) -> dict[str, Any]:
    preset_key = normalize_preset(preset)
    ratio_key = normalize_aspect_ratio(aspect_ratio)
    edit_prompt = studio_prompt(
        prompt,
        preset=preset_key,
        aspect_ratio=ratio_key,
    )
    result = await process_vision_request(
        content=content,
        filename=filename,
        mime_type=mime_type,
        prompt=edit_prompt,
        operation="edit",
        settings=settings,
    )
    url = str(result.get("url") or "")
    aspect_meta: dict[str, Any] = {
        "aspect_ratio": ratio_key,
        "aspect_applied": False,
    }
    if url.startswith("data:image/"):
        try:
            url, aspect_meta = fit_data_url_to_ratio(url, ratio_key)
        except Exception:
            pass
    return {
        **result,
        "url": url,
        "preset": preset_key,
        **aspect_meta,
    }
