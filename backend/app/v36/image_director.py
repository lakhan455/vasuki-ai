from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ImageDirection:
    version: str
    image_type: str
    aspect_hint: str
    realism: str
    camera: str
    lighting: str
    composition: str
    text_required: bool
    requested_resolution_signal: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _first_match(low: str, mapping: tuple[tuple[str, str], ...], default: str) -> str:
    for token, value in mapping:
        if token in low:
            return value
    return default


def direct_image_prompt(prompt: str) -> ImageDirection:
    text = " ".join(str(prompt or "").split()).strip()
    low = text.casefold()

    image_type = _first_match(low, (
        ("logo", "logo"),
        ("poster", "poster"),
        ("flyer", "poster"),
        ("product", "product"),
        ("anime", "illustration"),
        ("illustration", "illustration"),
        ("photo", "photoreal"),
        ("realistic", "photoreal"),
        ("cinematic", "cinematic"),
    ), "general")

    aspect = _first_match(low, (
        ("9:16", "9:16 portrait"),
        ("16:9", "16:9 landscape"),
        ("4:5", "4:5 portrait"),
        ("1:1", "1:1 square"),
        ("square", "1:1 square"),
        ("portrait", "portrait"),
        ("landscape", "landscape"),
    ), "provider-default")

    realism = (
        "ultra-photorealistic"
        if any(x in low for x in ("photoreal", "hyper-real", "realistic", "real photo"))
        else "stylized-as-requested"
    )
    camera = _first_match(low, (
        ("low angle", "low-angle perspective"),
        ("wide angle", "wide-angle perspective"),
        ("close-up", "close-up"),
        ("macro", "macro"),
        ("drone", "aerial/drone perspective"),
        ("85mm", "85mm portrait lens look"),
        ("35mm", "35mm environmental lens look"),
    ), "natural perspective appropriate to subject")

    lighting = _first_match(low, (
        ("golden hour", "golden-hour directional light"),
        ("sunset", "warm sunset light"),
        ("night", "controlled night lighting"),
        ("studio", "clean studio lighting"),
        ("neon", "neon practical lighting"),
        ("soft light", "soft diffused light"),
    ), "physically coherent lighting")

    composition = _first_match(low, (
        ("centered", "centered composition"),
        ("symmetrical", "symmetrical composition"),
        ("rule of thirds", "rule-of-thirds composition"),
        ("minimal", "minimal uncluttered composition"),
    ), "clear visual hierarchy with intentional subject separation")

    text_required = bool(
        re.search(r"\b(?:text|title|headline|tagline|write|written|says|label)\b", low)
    )

    resolution = (
        "8k-signal" if "8k" in low
        else "4k-signal" if "4k" in low
        else "high-detail"
    )

    return ImageDirection(
        version="v36",
        image_type=image_type,
        aspect_hint=aspect,
        realism=realism,
        camera=camera,
        lighting=lighting,
        composition=composition,
        text_required=text_required,
        requested_resolution_signal=resolution,
    )


def image_director_health() -> dict[str, Any]:
    return {
        "version": "v36",
        "name": "Visual Creative Director",
        "features": [
            "image-type-detection",
            "aspect-ratio-intent",
            "camera-direction",
            "lighting-direction",
            "composition-direction",
            "text-intent-detection",
            "resolution-signal-detection",
        ],
        "native_resolution_guarantee": False,
        "extra_provider_call_required": False,
    }
