from __future__ import annotations

from typing import Any


_FALLBACK_ATTRS = {
    "groq_fast": "v50_groq_fast_fallback_models",
    "groq": "v50_groq_fallback_models",
    "sambanova": "v50_sambanova_fallback_models",
    "cerebras": "v50_cerebras_fallback_models",
    "opencode_zen": "v50_opencode_zen_fallback_models",
    "zai_glm": "v50_zai_glm_fallback_models",
    "openrouter": "v50_openrouter_fallback_models",
    "mistral": "v50_mistral_fallback_models",
}


def _split(value: object) -> list[str]:
    rows: list[str] = []
    for item in str(value or "").replace("\n", ",").split(","):
        model = item.strip()
        if model and model not in rows:
            rows.append(model)
    return rows


def model_candidates(
    provider: str,
    settings: Any,
    *,
    primary: str = "",
) -> list[str]:
    first = str(primary or "").strip()
    if not bool(getattr(settings, "v50_model_fallback_enabled", True)):
        return [first] if first else []
    attr = _FALLBACK_ATTRS.get(str(provider or ""))
    fallbacks = _split(getattr(settings, attr, "")) if attr else []
    return list(dict.fromkeys(item for item in [first, *fallbacks] if item))


def should_try_model_fallback(
    *,
    status_code: int | None = None,
    error_text: str = "",
) -> bool:
    text = str(error_text or "").casefold()
    if status_code in {402, 404, 429}:
        return True
    if status_code in {401, 403}:
        return False
    return any(
        token in text
        for token in (
            "model not found",
            "unknown model",
            "unsupported model",
            "does not exist",
            "no endpoints found",
            "model is unavailable",
        )
    )


def configured_model_snapshot(settings: Any) -> dict[str, Any]:
    primary = {
        "groq_fast": getattr(settings, "groq_fast_model", ""),
        "groq": getattr(settings, "groq_model", ""),
        "sambanova": getattr(settings, "sambanova_model", ""),
        "cerebras": getattr(settings, "cerebras_model", ""),
        "opencode_zen": getattr(settings, "opencode_zen_model", ""),
        "zai_glm": getattr(settings, "zai_model", ""),
        "openrouter": getattr(settings, "openrouter_model", ""),
        "mistral": getattr(settings, "mistral_model", ""),
    }
    return {
        name: {
            "primary": str(model or ""),
            "candidates": model_candidates(name, settings, primary=str(model or "")),
        }
        for name, model in primary.items()
    }
