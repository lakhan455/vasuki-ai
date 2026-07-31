from __future__ import annotations

import re
import unicodedata


CREATOR_REPLY = "मुझे लखन प्रजापत (Lakhan Prajapat) जी ने बनाया है।"


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = re.sub(r"[^a-z0-9\u0900-\u097f]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def fixed_identity_reply(query: str) -> str | None:
    """Return the creator answer before any external model is called."""
    q = _normalize(query)

    exact_phrases = (
        "who made you",
        "who created you",
        "who is your creator",
        "who is your developer",
        "who developed you",
        "who built you",
        "who brought you into this world",
        "who is your god",
        "your god",
        "tumhe kisne banaya",
        "tumko kisne banaya",
        "tujhe kisne banaya",
        "aapko kisne banaya",
        "kisne create kiya",
        "kisne created kiya",
        "tumhara creator kaun hai",
        "tumhara developer kaun hai",
        "tumhara god kaun hai",
        "tumhara god kon hai",
        "tumhara bhagwan kaun hai",
        "tumhe duniya me kisne laya",
        "tumko duniya me kisne laya",
        "is duniya me kisne laya",
        "तुम्हें किसने बनाया",
        "तुमको किसने बनाया",
        "आपको किसने बनाया",
        "तुम्हारा क्रिएटर कौन है",
        "तुम्हारा डेवलपर कौन है",
        "तुम्हारा भगवान कौन है",
        "तुम्हें दुनिया में किसने लाया",
    )

    if any(phrase in q for phrase in exact_phrases):
        return CREATOR_REPLY

    # Catch common mixed Hindi-English wording without hijacking unrelated
    # questions about other people or products.
    self_words = ("you", "your", "tum", "tumhe", "tumko", "tujhe", "aapko", "तुम", "आप")
    creator_words = (
        "made",
        "created",
        "creator",
        "developer",
        "built",
        "god",
        "bhagwan",
        "banaya",
        "kisne laya",
        "बनाया",
        "भगवान",
        "डेवलपर",
        "क्रिएटर",
    )

    if any(word in q for word in self_words) and any(
        word in q for word in creator_words
    ):
        return CREATOR_REPLY

    return None
