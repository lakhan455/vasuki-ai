from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

_COLORS = (
    "black", "white", "red", "blue", "green", "yellow", "orange", "purple",
    "pink", "silver", "grey", "gray", "gold", "brown", "beige", "navy",
)
_COUNT_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_VEHICLE = re.compile(
    r"\b(?:bmw|mercedes(?:-benz)?|audi|porsche|tesla|ferrari|lamborghini|"
    r"bugatti|toyota|honda|ford|chevrolet|volkswagen|tata|mahindra)\s+"
    r"[A-Za-z0-9][A-Za-z0-9.+-]*(?:\s+[A-Za-z0-9][A-Za-z0-9.+-]*){0,2}\b",
    re.I,
)
_PRODUCT = re.compile(
    r"\b(?:iphone|ipad|macbook|galaxy|pixel|playstation|xbox)\s+"
    r"[A-Za-z0-9][A-Za-z0-9.+-]*(?:\s+[A-Za-z0-9][A-Za-z0-9.+-]*){0,2}\b",
    re.I,
)
_PROPER_PAIR = re.compile(r"\b[A-Z][A-Za-z'-]{2,}\s+[A-Z][A-Za-z'-]{2,}\b")
_CHARACTER_SIGNAL = re.compile(
    r"\b(?:anime|manga|naruto|hokage|shinobi|uchiha|namikaze|doraemon|"
    r"goku|vegeta|gojo|jujutsu|akatsuki|one piece|luffy|zoro)\b",
    re.I,
)


@dataclass(frozen=True, slots=True)
class ImageConstraints:
    colors: tuple[str, ...]
    count: int | None
    vehicle_model: str
    product_model: str
    named_subjects: tuple[str, ...]
    exact_identity: bool
    character_signal: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["colors"] = list(self.colors)
        data["named_subjects"] = list(self.named_subjects)
        return data


def extract_image_constraints(prompt: str) -> ImageConstraints:
    text = " ".join(str(prompt or "").split())
    low = text.casefold()
    colors = tuple(color for color in _COLORS if re.search(rf"\b{re.escape(color)}\b", low))

    count: int | None = None
    numeric = re.search(r"\b([1-9]|10)\s+(?:people|persons|characters|cars|vehicles|objects|dogs|cats)\b", low)
    if numeric:
        count = int(numeric.group(1))
    else:
        for word, value in _COUNT_WORDS.items():
            if re.search(rf"\b{word}\s+(?:people|persons|characters|cars|vehicles|objects|dogs|cats)\b", low):
                count = value
                break

    vehicle_match = _VEHICLE.search(text)
    product_match = _PRODUCT.search(text)
    vehicle_model = vehicle_match.group(0).strip() if vehicle_match else ""
    product_model = product_match.group(0).strip() if product_match else ""

    names: list[str] = []
    for match in _PROPER_PAIR.finditer(text):
        value = match.group(0).strip()
        if value.casefold() not in {
            "create image", "generate image", "high quality", "hidden leaf", "fourth hokage"
        }:
            names.append(value)

    for value in (vehicle_model, product_model):
        if value and value.casefold() not in {x.casefold() for x in names}:
            names.append(value)

    character_signal = bool(_CHARACTER_SIGNAL.search(text))
    exact_identity = bool(
        vehicle_model
        or product_model
        or (names and character_signal)
        or re.search(r"\b(?:exact|canonical|accurate|specific model|same character|identity)\b", low)
    )

    return ImageConstraints(
        colors=colors,
        count=count,
        vehicle_model=vehicle_model,
        product_model=product_model,
        named_subjects=tuple(dict.fromkeys(names)),
        exact_identity=exact_identity,
        character_signal=character_signal,
    )


def build_identity_locked_prompt(prompt: str, image_type: str, style_suffix: str) -> str:
    base = " ".join(str(prompt or "").split()).strip()
    if not base:
        return base

    c = extract_image_constraints(base)
    locks: list[str] = [
        "LATEST REQUEST AUTHORITY: use only the attributes in this current image request; do not inherit a color, model, outfit, pose, count, or subject from an earlier request.",
        "SUBJECT FIDELITY: every explicitly named subject, brand, model, fictional character, relationship, pose, outfit, and required attribute is mandatory; do not substitute a similar subject.",
    ]

    if c.vehicle_model:
        locks.append(
            f"VEHICLE MODEL LOCK: the main vehicle must be exactly '{c.vehicle_model}'; do not replace it with a nearby series, generation, sedan/coupe variant, or generic vehicle."
        )
    if c.product_model:
        locks.append(
            f"PRODUCT MODEL LOCK: the requested product must be exactly '{c.product_model}'; do not substitute a similar product or generation."
        )
    if c.named_subjects:
        locks.append(
            "IDENTITY LOCK: preserve the canonical distinguishing visual features of "
            + ", ".join(c.named_subjects[:4])
            + "; never replace a named character/person with a generic lookalike."
        )
    if c.colors:
        locks.append(
            "COLOR LOCK: the main requested subject must use exactly the requested color(s): "
            + ", ".join(c.colors)
            + ". Never substitute another color."
        )
    if c.count is not None:
        locks.append(f"COUNT LOCK: show exactly {c.count} requested primary subject(s), not more and not fewer.")

    locks.append(
        "QUALITY GUARD: avoid accidental text, watermarks, duplicate limbs/objects, malformed geometry, low-resolution artifacts, and clutter unless explicitly requested."
    )

    lock_text = " ".join(locks)
    style = str(style_suffix or "").strip()
    reserve = min(900, len(lock_text) + len(style) + 24)
    base_budget = max(700, 2048 - reserve)
    clipped_base = base[:base_budget].rstrip()
    return f"{clipped_base}. {style}. {lock_text}"[:2048]
