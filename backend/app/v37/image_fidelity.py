from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from app.v13.image_identity import build_identity_locked_prompt, extract_image_constraints
from app.v36.image_director import ImageDirection


@dataclass(frozen=True, slots=True)
class FidelityPlan:
    version: str
    identity_lock: bool
    exact_text_lock: bool
    count_lock: int | None
    color_locks: tuple[str, ...]
    subject_locks: tuple[str, ...]
    prompt: str

    def to_dict(self, *, include_prompt: bool = False) -> dict[str, Any]:
        data = asdict(self)
        data["color_locks"] = list(self.color_locks)
        data["subject_locks"] = list(self.subject_locks)
        if not include_prompt:
            data.pop("prompt", None)
        return data


def _quoted_text(prompt: str) -> list[str]:
    matches = re.findall(r'["“]([^"”]{1,120})["”]', str(prompt or ""))
    return [value.strip() for value in matches if value.strip()][:4]


def build_fidelity_prompt(prompt: str, direction: ImageDirection) -> FidelityPlan:
    constraints = extract_image_constraints(prompt)
    style = (
        f"{direction.realism}; {direction.camera}; {direction.lighting}; "
        f"{direction.composition}; aspect intent {direction.aspect_hint}"
    )
    locked = build_identity_locked_prompt(prompt, direction.image_type, style)
    quoted = _quoted_text(prompt)

    if direction.text_required and quoted:
        text_guard = (
            " EXACT TEXT LOCK: render only the explicitly requested visible wording exactly as provided: "
            + " | ".join(quoted)
            + "; preserve spelling, capitalization, and word order; do not invent additional text."
        )
        locked = (
            locked[: max(0, 2048 - len(text_guard))].rstrip(" .")
            + "."
            + text_guard
        )[:2048]

    return FidelityPlan(
        version="v37",
        identity_lock=constraints.exact_identity,
        exact_text_lock=bool(direction.text_required and quoted),
        count_lock=constraints.count,
        color_locks=constraints.colors,
        subject_locks=constraints.named_subjects,
        prompt=locked,
    )


def image_fidelity_health() -> dict[str, Any]:
    return {
        "version": "v37",
        "name": "Image Fidelity and Identity Engine",
        "features": [
            "v13-identity-lock-reuse",
            "vehicle-product-character-locks",
            "count-and-color-locks",
            "exact-visible-text-lock-when-explicit",
            "latest-request-authority",
        ],
        "identity_guarantee": False,
        "extra_provider_call_required": False,
    }
