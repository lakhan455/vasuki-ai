from __future__ import annotations

import asyncio
import base64
from io import BytesIO
from typing import Awaitable, Callable

import httpx
from huggingface_hub import InferenceClient

from app.config import Settings


RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


def _safe_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            detail = (
                payload.get("errors")
                or payload.get("messages")
                or payload.get("error")
                or payload.get("message")
                or payload.get("detail")
                or payload
            )
            return str(detail)[:900]
    except Exception:
        pass

    return (response.text or f"HTTP {response.status_code}")[:900]


def _response_error(provider: str, response: httpx.Response) -> RuntimeError:
    detail = _safe_detail(response)

    if provider == "cloudflare":
        if response.status_code == 401:
            return RuntimeError(
                "Cloudflare authorization failed. Check CLOUDFLARE_ACCOUNT_ID "
                "and the Workers AI API token permissions."
            )
        if response.status_code == 403:
            return RuntimeError(
                "Cloudflare denied the image request. Check Workers AI access, "
                "token permissions and account billing/quota."
            )
        if response.status_code == 429:
            return RuntimeError(
                "Cloudflare image generation is temporarily rate-limited or "
                "the daily Workers AI allocation is exhausted."
            )

    if provider == "deepai" and response.status_code == 402:
        return RuntimeError(
            "DeepAI image access requires an active paid balance/subscription."
        )

    return RuntimeError(f"{provider} HTTP {response.status_code}: {detail}")


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                return min(12.0, max(1.0, float(retry_after)))
            except ValueError:
                pass
    return (1.5, 3.0, 5.0)[min(attempt, 2)]


async def _post_with_retry(
    url: str,
    *,
    headers: dict[str, str],
    json_body: dict | None,
    form_body: dict | None,
    timeout_seconds: float,
    attempts: int,
) -> httpx.Response:
    last_response: httpx.Response | None = None
    last_error: Exception | None = None

    timeout = httpx.Timeout(
        connect=15.0,
        read=timeout_seconds,
        write=20.0,
        pool=15.0,
    )

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(max(1, attempts)):
            try:
                response = await client.post(
                    url,
                    headers=headers,
                    json=json_body,
                    data=form_body,
                )
                last_response = response

                if (
                    response.status_code not in RETRYABLE_STATUS
                    or attempt >= attempts - 1
                ):
                    return response

                await asyncio.sleep(_retry_delay(response, attempt))
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt >= attempts - 1:
                    raise RuntimeError(
                        "Image provider connection timed out after automatic retries."
                    ) from exc
                await asyncio.sleep(_retry_delay(None, attempt))

    if last_response is not None:
        return last_response
    raise RuntimeError(
        f"Image provider could not be reached: {last_error or 'unknown network error'}"
    )


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

    response = await _post_with_retry(
        url,
        headers=headers,
        json_body=body,
        form_body=None,
        timeout_seconds=float(settings.image_timeout_seconds),
        attempts=int(settings.image_retry_attempts),
    )

    if response.is_error:
        raise _response_error("cloudflare", response)

    try:
        payload = response.json()
    except Exception as exc:
        raise RuntimeError("Cloudflare returned an invalid image response.") from exc

    if not payload.get("success", True):
        raise RuntimeError(
            f"Cloudflare rejected the image request: {payload.get('errors')}"
        )

    image_b64 = payload.get("result", {}).get("image")
    if not image_b64:
        raise RuntimeError("Cloudflare response did not contain result.image")

    return {
        "url": f"data:image/jpeg;base64,{image_b64}",
        "provider": "cloudflare",
    }


async def image_huggingface(prompt: str, settings: Settings) -> dict:
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
        encoded = await asyncio.wait_for(
            asyncio.to_thread(generate),
            timeout=float(settings.image_timeout_seconds),
        )
    except asyncio.TimeoutError as exc:
        raise RuntimeError("Hugging Face image generation timed out.") from exc
    except Exception as exc:
        raise RuntimeError(
            "Hugging Face image generation failed. The account may have "
            f"insufficient inference credits. Original error: {str(exc)[:500]}"
        ) from exc

    return {
        "url": f"data:image/png;base64,{encoded}",
        "provider": "huggingface",
    }


async def image_deepai(prompt: str, settings: Settings) -> dict:
    if not settings.deepai_api:
        raise RuntimeError("DEEPAI_API is not configured")

    response = await _post_with_retry(
        "https://api.deepai.org/api/text2img",
        headers={"api-key": settings.deepai_api},
        json_body=None,
        form_body={"text": prompt},
        timeout_seconds=float(settings.image_timeout_seconds),
        attempts=2,
    )

    if response.is_error:
        raise _response_error("deepai", response)

    payload = response.json()
    output_url = payload.get("output_url")
    if not output_url:
        raise RuntimeError("DeepAI response did not contain output_url")

    return {"url": output_url, "provider": "deepai"}


async def route_image(provider: str, prompt: str, settings: Settings) -> dict:
    providers: dict[str, Callable[[str, Settings], Awaitable[dict]]] = {
        "cloudflare": image_cloudflare,
        "huggingface": image_huggingface,
        "deepai": image_deepai,
    }

    if provider != "auto" and provider not in providers:
        raise RuntimeError(f"Unknown image provider: {provider}")

    order = (
        [provider]
        if provider != "auto"
        else ["cloudflare", "huggingface", "deepai"]
    )

    errors: list[str] = []
    for name in order:
        try:
            return await asyncio.wait_for(
                providers[name](prompt, settings),
                timeout=float(settings.image_timeout_seconds) + 15.0,
            )
        except asyncio.TimeoutError:
            errors.append(f"{name}: timed out")
        except Exception as exc:
            errors.append(f"{name}: {str(exc)[:700]}")

        # A very small pause prevents rapid provider hammering while still
        # keeping the user request responsive.
        await asyncio.sleep(0.4)

    raise RuntimeError("All image providers failed. " + " | ".join(errors))
