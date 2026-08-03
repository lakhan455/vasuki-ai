from __future__ import annotations

import asyncio
import base64
from io import BytesIO
from typing import Awaitable, Callable

import httpx
from huggingface_hub import InferenceClient

from app.config import Settings


def _response_error(provider: str, response: httpx.Response) -> RuntimeError:
    """Return a readable provider error without exposing credentials."""
    detail = response.text[:800]
    try:
        payload = response.json()
        detail = (
            payload.get("errors")
            or payload.get("messages")
            or payload.get("error")
            or payload.get("err")
            or payload.get("status")
            or payload
        )
    except Exception:
        pass

    if provider == "cloudflare" and response.status_code == 401:
        return RuntimeError(
            "Cloudflare HTTP 401: token/account authorization failed. "
            "Create a new Workers AI API token with Workers AI Read + Edit permissions, "
            "confirm CLOUDFLARE_ACCOUNT_ID, update .env, and restart the backend."
        )

    if provider == "deepai" and response.status_code == 402:
        return RuntimeError(
            "DeepAI HTTP 402: API image access requires an active paid balance/subscription."
        )

    return RuntimeError(f"{provider} HTTP {response.status_code}: {detail}")


async def image_cloudflare(prompt: str, settings: Settings) -> dict:
    if not settings.cloudflare_account_id or not settings.cloudflare_workers_ai:
        raise RuntimeError(
            "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_WORKERS_AI are not configured"
        )

    model = settings.cloudflare_image_model
    if not model.startswith("@cf/"):
        model = f"@cf/{model.lstrip('/')}"

    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{settings.cloudflare_account_id}/ai/run/{model}"
    )
    headers = {
        "Authorization": f"Bearer {settings.cloudflare_workers_ai}",
        "Content-Type": "application/json",
    }
    body = {
        "prompt": prompt[:2048],
        "steps": 4,
    }

    async with httpx.AsyncClient(
        timeout=max(settings.request_timeout_seconds, 180)
    ) as client:
        response = await client.post(url, headers=headers, json=body)

    if response.is_error:
        raise _response_error("cloudflare", response)

    payload = response.json()
    if not payload.get("success", True):
        raise RuntimeError(f"Cloudflare rejected the request: {payload.get('errors')}")

    image_b64 = payload.get("result", {}).get("image")
    if not image_b64:
        raise RuntimeError("Cloudflare response did not contain result.image")

    return {
        "url": f"data:image/jpeg;base64,{image_b64}",
        "provider": "cloudflare",
    }


async def image_huggingface(prompt: str, settings: Settings) -> dict:
    """
    Use Hugging Face Inference Providers instead of the retired direct
    /hf-inference/models/... route.
    """
    if not settings.hugging_face_inference_api:
        raise RuntimeError("HUGGING_FACE_INFERENCE_API is not configured")

    def generate() -> str:
        client = InferenceClient(
            provider="auto",
            api_key=settings.hugging_face_inference_api,
        )
        image = client.text_to_image(
            prompt=prompt,
            model=settings.hf_image_model,
        )
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    try:
        encoded = await asyncio.to_thread(generate)
    except Exception as exc:
        raise RuntimeError(
            "Hugging Face Inference Providers failed. Confirm that the token has "
            "'Inference Providers' permission and that the account/key has available credits. "
            f"Original error: {exc}"
        ) from exc

    return {
        "url": f"data:image/png;base64,{encoded}",
        "provider": "huggingface",
    }


async def image_deepai(prompt: str, settings: Settings) -> dict:
    if not settings.deepai_api:
        raise RuntimeError("DEEPAI_API is not configured")

    headers = {"api-key": settings.deepai_api}
    data = {"text": prompt}

    async with httpx.AsyncClient(
        timeout=max(settings.request_timeout_seconds, 120)
    ) as client:
        response = await client.post(
            "https://api.deepai.org/api/text2img",
            headers=headers,
            data=data,
        )

    if response.is_error:
        raise _response_error("deepai", response)

    payload = response.json()
    output_url = payload.get("output_url")
    if not output_url:
        raise RuntimeError("DeepAI response did not contain output_url")

    return {"url": output_url, "provider": "deepai"}


async def route_image(provider: str, prompt: str, settings: Settings) -> dict:
    providers: dict[
        str, Callable[[str, Settings], Awaitable[dict]]
    ] = {
        "cloudflare": image_cloudflare,
        "huggingface": image_huggingface,
        "deepai": image_deepai,
    }

    # Cloudflare is first because it has a current hosted FLUX model and
    # works on Cloudflare Free/Paid plans when the token is configured.
    order = [provider] if provider != "auto" else [
        "cloudflare",
        "huggingface",
        "deepai",
    ]

    errors: list[str] = []
    for name in order:
        try:
            return await providers[name](prompt, settings)
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    raise RuntimeError("All image providers failed. " + " | ".join(errors))
