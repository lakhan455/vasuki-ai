from __future__ import annotations

from typing import Any

from app.v35.code_runtime import build_advanced_code_context
from app.v38.image_runtime import build_image_generation_plan
from app.v39.creator_critic import review_code_plan, review_image_plan

_CODE_SIGNALS = (
    "code", "bug", "debug", "fix", "api", "fastapi", "react", "next.js",
    "typescript", "python", "project", "repo", "repository", "build failed",
    "traceback", "exception",
)
_IMAGE_SIGNALS = (
    "image", "photo", "poster", "logo", "illustration", "wallpaper",
    "generate picture", "create picture", "cinematic", "photorealistic",
)


def _last_user(messages: list[dict[str, Any]]) -> str:
    return next(
        (
            str(item.get("content") or "")
            for item in reversed(messages)
            if item.get("role") == "user"
        ),
        "",
    )


def _mode(prompt: str) -> str:
    low = str(prompt or "").casefold()
    code = any(token in low for token in _CODE_SIGNALS)
    image = any(token in low for token in _IMAGE_SIGNALS)
    if code and image:
        return "code+image"
    if image:
        return "image"
    if code:
        return "code"
    return "general"


def creator_inspect(
    prompt: str,
    *,
    provider: str = "auto",
    existing_files: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    mode = _mode(prompt)
    result: dict[str, Any] = {"version": "v40", "mode": mode}

    if mode in {"code", "code+image"}:
        _context, code = build_advanced_code_context(prompt, existing_files)
        result["coding"] = code
        result["coding_review"] = review_code_plan(code).to_dict()

    if mode in {"image", "code+image"}:
        image = build_image_generation_plan(prompt, provider=provider)
        image_data = image.to_dict(include_prompt=False)
        result["image"] = image_data
        result["image_review"] = review_image_plan(image_data).to_dict()

    return result


def build_creator_context(messages: list[dict[str, Any]]) -> str:
    prompt = _last_user(messages).strip()
    mode = _mode(prompt)
    if mode == "general":
        return ""

    lines = [
        "VASUKI V40 CREATOR RUNTIME:",
        f"Creator mode: {mode}.",
    ]
    if mode in {"code", "code+image"}:
        lines.append(
            "CODING: inspect evidence before edits; prefer minimal compatible changes; "
            "preserve interfaces; plan regression validation; never claim tests/build/deploy ran without evidence."
        )
    if mode in {"image", "code+image"}:
        lines.append(
            "IMAGE: obey the latest visual request exactly; preserve named model/color/count/identity constraints; "
            "use intentional camera, lighting and composition; avoid accidental text, watermarks, duplicates and malformed geometry."
        )
    return "\n".join(lines)


def creator_runtime_health() -> dict[str, Any]:
    return {
        "version": "v40",
        "name": "Vasuki Advanced Creator Runtime",
        "layers": [
            "v31-coding-spec-compiler",
            "v32-code-impact-engine",
            "v33-minimal-patch-brain",
            "v34-evidence-verification-engine",
            "v35-advanced-coding-runtime",
            "v36-visual-creative-director",
            "v37-image-fidelity-engine",
            "v38-advanced-image-runtime",
            "v39-creator-quality-critic",
            "v40-unified-creator-runtime",
        ],
        "production_chat_integration": True,
        "v16_v17_coding_builder_integration": True,
        "production_image_route_integration": True,
        "v13_identity_lock_preserved": True,
        "v30_autonomy_preserved": True,
        "db_migration_required": False,
        "new_api_key_required": False,
        "extra_provider_call_required": False,
        "silent_memory_write": False,
        "arbitrary_server_code_execution": False,
        "automatic_deploy_without_confirmation": False,
        "native_image_resolution_guarantee": False,
        "hidden_chain_of_thought_exposed": False,
    }
