from __future__ import annotations

import base64
import random
import re
from io import BytesIO
from typing import Any

import httpx
from PIL import Image, ImageOps

from app.config import Settings
from app.services.chat import route_chat


IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}
SUPPORTED_MIME_TYPES = IMAGE_MIME_TYPES | {"application/pdf"}

VISION_SYSTEM_PROMPT = """You are Vasuki Vision, a careful multimodal assistant.
Inspect the supplied image or document directly and answer in the user's language.

Accuracy rules:
1. Read every visible word, number, symbol, table, diagram and option carefully.
2. Never invent text hidden by blur, cropping, glare or low resolution. Clearly mark unreadable portions.
3. For question sheets, answer every visible question in the same order. Include question numbers, selected options and necessary calculations or reasoning.
4. For maths and science, re-check arithmetic, units, signs and final answers.
5. For screenshots, forms, bills, charts and documents, preserve the visible structure and terminology.
6. For normal photos, describe only what is actually visible and then answer the user's specific question.
7. Do not identify unknown real people by name from their face.
"""

EDIT_PATTERNS = (
    r"\bedit\b",
    r"\bmodify\b",
    r"\bretouch\b",
    r"\benhance\b",
    r"\bupscale\b",
    r"\brestore\b",
    r"\brecolor\b",
    r"\bcrop\b",
    r"\bremove\b",
    r"\breplace\b",
    r"\badd\b",
    r"\banime\b",
    r"\bcartoon\b",
    r"\b4k\b",
    r"\bhd\b",
    r"\bgora\b",
    r"\bgori\b",
    r"background\s+(change|remove|replace|hata|badal)",
    r"(rang|colour|color)\s+(change|badal)",
    r"(kapde|dress|hair|baal)\s+(change|badal)",
    r"(photo|image|picture)\s+ko\s+(change|edit|saaf|clear|gora)",
)


def _safe_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and error.get("message"):
                return str(error["message"])[:700]
            for key in ("message", "detail", "errors"):
                if payload.get(key):
                    return str(payload[key])[:700]
    except Exception:
        pass
    return (response.text or f"HTTP {response.status_code}")[:700]


def _looks_like_edit(prompt: str) -> bool:
    normalized = prompt.casefold().strip()
    return any(re.search(pattern, normalized) for pattern in EDIT_PATTERNS)


def _analysis_prompt(user_prompt: str) -> str:
    prompt = user_prompt.strip() or "Is image/file ko detail me analyze karo."
    return (
        f"{prompt}\n\n"
        "Apply the Vasuki Vision accuracy rules. If this is a question paper, "
        "worksheet or answer sheet, solve every visible question in order and "
        "do not skip any readable item."
    )


def _edit_prompt(user_prompt: str) -> str:
    prompt = user_prompt.strip() or "Enhance this image naturally."
    return (
        "Edit input image 0 according to this instruction: "
        f"{prompt}. Preserve the original person's identity, facial structure, "
        "pose and important details unless the instruction explicitly asks to "
        "change them. Keep lighting, edges and perspective realistic. Do not add "
        "unrequested people, text, logos or objects. Return only the edited image."
    )


def _extract_gemini_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""

    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(
        str(part.get("text") or "")
        for part in parts
        if isinstance(part, dict)
    ).strip()


def _find_image_block(value: Any) -> tuple[str, str] | None:
    if isinstance(value, dict):
        data = value.get("data")
        mime = value.get("mime_type") or value.get("mimeType")
        block_type = str(value.get("type") or "").casefold()
        if isinstance(data, str) and data and (
            isinstance(mime, str) and mime.startswith("image/")
            or "image" in block_type
        ):
            return data, str(mime or "image/png")

        for item in value.values():
            found = _find_image_block(item)
            if found:
                return found

    if isinstance(value, list):
        for item in value:
            found = _find_image_block(item)
            if found:
                return found

    return None


async def _gemini_analyze(
    content: bytes,
    mime_type: str,
    prompt: str,
    settings: Settings,
) -> dict:
    if not settings.google_gemini_api:
        raise RuntimeError("Google Gemini vision is not configured")

    model = settings.gemini_vision_model
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    payload = {
        "systemInstruction": {
            "parts": [{"text": VISION_SYSTEM_PROMPT}],
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": base64.b64encode(content).decode("ascii"),
                        }
                    },
                    {"text": _analysis_prompt(prompt)},
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": min(settings.max_output_tokens, 8192),
        },
    }
    headers = {
        "x-goog-api-key": settings.google_gemini_api,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(
        timeout=float(settings.vision_timeout_seconds)
    ) as client:
        response = await client.post(url, headers=headers, json=payload)

    if response.is_error:
        raise RuntimeError(
            f"Gemini vision HTTP {response.status_code}: {_safe_error(response)}"
        )

    answer = _extract_gemini_text(response.json())
    if not answer:
        raise RuntimeError("Gemini vision returned an empty answer")

    return {
        "answer": answer,
        "provider": f"gemini-vision:{model}",
        "operation": "analyze",
    }


async def _cloudflare_analyze(
    content: bytes,
    mime_type: str,
    prompt: str,
    settings: Settings,
) -> dict:
    if not settings.cloudflare_account_id or not settings.cloudflare_workers_ai:
        raise RuntimeError("Cloudflare Workers AI vision is not configured")
    if mime_type not in IMAGE_MIME_TYPES:
        raise RuntimeError("Cloudflare vision fallback only supports images")

    model = settings.cloudflare_vision_model
    if not model.startswith("@cf/"):
        model = f"@cf/{model.lstrip('/')}"

    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{settings.cloudflare_account_id}/ai/run/{model}"
    )
    image_data = (
        f"data:{mime_type};base64,"
        + base64.b64encode(content).decode("ascii")
    )
    payload = {
        "task": "query",
        "image": image_data,
        "question": VISION_SYSTEM_PROMPT + "\n\n" + _analysis_prompt(prompt),
        "reasoning": False,
        "temperature": 0.1,
        "max_tokens": min(settings.max_output_tokens, 8192),
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {settings.cloudflare_workers_ai}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(
        timeout=float(settings.vision_timeout_seconds)
    ) as client:
        response = await client.post(url, headers=headers, json=payload)

    if response.is_error:
        raise RuntimeError(
            f"Cloudflare vision HTTP {response.status_code}: {_safe_error(response)}"
        )

    payload = response.json()
    result = payload.get("result") or payload
    answer = result.get("answer") if isinstance(result, dict) else None
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Cloudflare vision returned an empty answer")

    return {
        "answer": answer.strip(),
        "provider": f"cloudflare-vision:{model}",
        "operation": "analyze",
    }


async def _ocr_space_text(
    content: bytes,
    filename: str,
    mime_type: str,
    settings: Settings,
) -> str:
    if not settings.ocr_space_api:
        raise RuntimeError("OCR.Space is not configured")

    files = {
        "file": (
            filename or "upload",
            content,
            mime_type or "application/octet-stream",
        )
    }
    data = {
        "apikey": settings.ocr_space_api,
        "language": "eng",
        "isOverlayRequired": "false",
        "OCREngine": "2",
    }

    async with httpx.AsyncClient(
        timeout=float(settings.vision_timeout_seconds)
    ) as client:
        response = await client.post(
            "https://api.ocr.space/parse/image",
            data=data,
            files=files,
        )

    if response.is_error:
        raise RuntimeError(
            f"OCR.Space HTTP {response.status_code}: {_safe_error(response)}"
        )

    payload = response.json()
    parsed = payload.get("ParsedResults") or []
    text = "\n".join(
        str(item.get("ParsedText") or "")
        for item in parsed
        if isinstance(item, dict)
    ).strip()
    if not text:
        raise RuntimeError(
            f"OCR.Space returned no readable text: {payload.get('ErrorMessage')}"
        )
    return text


async def _ocr_then_chat(
    content: bytes,
    filename: str,
    mime_type: str,
    prompt: str,
    settings: Settings,
) -> dict:
    text = await _ocr_space_text(
        content,
        filename,
        mime_type,
        settings,
    )
    messages = [
        {
            "role": "user",
            "content": (
                VISION_SYSTEM_PROMPT
                + "\n\nUSER REQUEST:\n"
                + _analysis_prompt(prompt)
                + "\n\nOCR TEXT:\n"
                + text[:35000]
            ),
        }
    ]
    answer, provider = await route_chat(
        "auto",
        messages,
        settings,
        require_current=False,
    )
    return {
        "answer": answer,
        "provider": f"ocr.space+{provider}",
        "operation": "analyze",
    }


def _prepare_cloudflare_image(content: bytes) -> tuple[bytes, int, int]:
    try:
        with Image.open(BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            original_width, original_height = image.size

            input_image = image.copy()
            input_image.thumbnail((511, 511), Image.Resampling.LANCZOS)
            input_buffer = BytesIO()
            input_image.save(input_buffer, format="JPEG", quality=92)

            scale = min(1024 / original_width, 1024 / original_height)
            width = max(256, min(1920, round(original_width * scale / 64) * 64))
            height = max(256, min(1920, round(original_height * scale / 64) * 64))
            return input_buffer.getvalue(), width, height
    except Exception as exc:
        raise RuntimeError("The uploaded image could not be decoded") from exc


async def _cloudflare_edit(
    content: bytes,
    prompt: str,
    settings: Settings,
) -> dict:
    if not settings.cloudflare_account_id or not settings.cloudflare_workers_ai:
        raise RuntimeError("Cloudflare image editing is not configured")

    model = settings.cloudflare_edit_model
    if not model.startswith("@cf/"):
        model = f"@cf/{model.lstrip('/')}"

    prepared, width, height = _prepare_cloudflare_image(content)
    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{settings.cloudflare_account_id}/ai/run/{model}"
    )
    headers = {
        "Authorization": f"Bearer {settings.cloudflare_workers_ai}",
    }
    data = {
        "prompt": _edit_prompt(prompt),
        "width": str(width),
        "height": str(height),
        "guidance": "4.0",
        "seed": str(random.randint(1, 2_147_483_647)),
    }
    files = {
        "input_image_0": ("input.jpg", prepared, "image/jpeg"),
    }

    async with httpx.AsyncClient(
        timeout=float(settings.vision_timeout_seconds)
    ) as client:
        response = await client.post(
            url,
            headers=headers,
            data=data,
            files=files,
        )

    if response.is_error:
        raise RuntimeError(
            f"Cloudflare edit HTTP {response.status_code}: {_safe_error(response)}"
        )

    payload = response.json()
    result = payload.get("result") or {}
    image_b64 = result.get("image") if isinstance(result, dict) else None
    if not isinstance(image_b64, str) or not image_b64:
        raise RuntimeError("Cloudflare edit response did not contain an image")

    return {
        "answer": "Edited image ready.",
        "url": f"data:image/png;base64,{image_b64}",
        "provider": f"cloudflare-edit:{model}",
        "operation": "edit",
    }


async def _gemini_edit(
    content: bytes,
    mime_type: str,
    prompt: str,
    settings: Settings,
) -> dict:
    if not settings.google_gemini_api:
        raise RuntimeError("Gemini image editing is not configured")

    model = settings.gemini_image_edit_model
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    headers = {
        "x-goog-api-key": settings.google_gemini_api,
        "Content-Type": "application/json",
    }
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": _edit_prompt(prompt)},
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": base64.b64encode(content).decode("ascii"),
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "responseFormat": {
                "image": {
                    "imageSize": "1K",
                }
            },
        },
    }

    async with httpx.AsyncClient(
        timeout=float(settings.vision_timeout_seconds)
    ) as client:
        response = await client.post(url, headers=headers, json=payload)

    if response.is_error:
        raise RuntimeError(
            f"Gemini edit HTTP {response.status_code}: {_safe_error(response)}"
        )

    found = _find_image_block(response.json())
    if not found:
        raise RuntimeError("Gemini edit response did not contain an image")

    image_b64, output_mime = found
    return {
        "answer": "Edited image ready.",
        "url": f"data:{output_mime};base64,{image_b64}",
        "provider": f"gemini-edit:{model}",
        "operation": "edit",
    }


async def process_vision_request(
    *,
    content: bytes,
    filename: str,
    mime_type: str,
    prompt: str,
    operation: str,
    settings: Settings,
) -> dict:
    normalized_mime = (mime_type or "").split(";", 1)[0].strip().casefold()
    if normalized_mime == "image/jpg":
        normalized_mime = "image/jpeg"

    if normalized_mime not in SUPPORTED_MIME_TYPES:
        raise RuntimeError(
            "Unsupported file type. Upload JPG, PNG, WEBP, GIF or PDF."
        )

    normalized_operation = (operation or "auto").strip().casefold()
    if normalized_operation not in {"auto", "analyze", "edit"}:
        raise RuntimeError("operation must be auto, analyze or edit")

    should_edit = (
        normalized_operation == "edit"
        or (
            normalized_operation == "auto"
            and normalized_mime in IMAGE_MIME_TYPES
            and _looks_like_edit(prompt)
        )
    )

    errors: list[str] = []

    if should_edit:
        for name, provider in (
            ("cloudflare", _cloudflare_edit),
            ("gemini", _gemini_edit),
        ):
            try:
                if name == "cloudflare":
                    return await provider(content, prompt, settings)
                return await provider(content, normalized_mime, prompt, settings)
            except Exception as exc:
                errors.append(f"{name}: {str(exc)[:700]}")

        raise RuntimeError(
            "Image editing failed. " + " | ".join(errors)
        )

    analyzers = [
        ("gemini", _gemini_analyze),
    ]
    if normalized_mime in IMAGE_MIME_TYPES:
        analyzers.append(("cloudflare", _cloudflare_analyze))

    for name, analyzer in analyzers:
        try:
            return await analyzer(
                content,
                normalized_mime,
                prompt,
                settings,
            )
        except Exception as exc:
            errors.append(f"{name}: {str(exc)[:700]}")

    try:
        return await _ocr_then_chat(
            content,
            filename,
            normalized_mime,
            prompt,
            settings,
        )
    except Exception as exc:
        errors.append(f"ocr: {str(exc)[:700]}")

    raise RuntimeError(
        "Image/file analysis failed. " + " | ".join(errors)
    )
