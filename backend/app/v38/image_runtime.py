from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.v36.image_director import direct_image_prompt
from app.v37.image_fidelity import build_fidelity_prompt


@dataclass(frozen=True, slots=True)
class ImageGenerationPlan:
    version: str
    requested_provider: str
    routing_policy: str
    quality_mode: str
    aspect_hint: str
    image_type: str
    requested_resolution_signal: str
    enhanced_prompt: str
    fidelity: dict[str, Any]

    def to_dict(self, *, include_prompt: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if not include_prompt:
            data.pop("enhanced_prompt", None)
        return data


def build_image_generation_plan(
    prompt: str,
    *,
    provider: str = "auto",
) -> ImageGenerationPlan:
    direction = direct_image_prompt(prompt)
    fidelity = build_fidelity_prompt(prompt, direction)

    quality_mode = (
        "identity-critical"
        if fidelity.identity_lock
        else "text-critical"
        if fidelity.exact_text_lock
        else "high-fidelity"
    )
    routing = (
        "preserve-explicit-provider"
        if provider != "auto"
        else "existing-omniroute-first-when-enabled-then-existing-resilient-fallback"
    )

    return ImageGenerationPlan(
        version="v38",
        requested_provider=provider,
        routing_policy=routing,
        quality_mode=quality_mode,
        aspect_hint=direction.aspect_hint,
        image_type=direction.image_type,
        requested_resolution_signal=direction.requested_resolution_signal,
        enhanced_prompt=fidelity.prompt[:2048],
        fidelity=fidelity.to_dict(include_prompt=False),
    )


def image_runtime_health() -> dict[str, Any]:
    return {
        "version": "v38",
        "name": "Advanced Image Generation Runtime",
        "features": [
            "creative-direction-before-generation",
            "identity-fidelity-before-generation",
            "explicit-provider-preservation",
            "existing-omniroute-and-provider-fallback-preservation",
            "quality-mode-metadata",
        ],
        "new_image_provider_required": False,
        "new_api_key_required": False,
        "native_size_parameter_added": False,
    }
