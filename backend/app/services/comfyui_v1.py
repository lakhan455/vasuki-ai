from __future__ import annotations

import asyncio
import base64
import random
import uuid
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings


def _base_url(settings: Settings) -> str:
    return (settings.comfyui_base_url or "").rstrip("/")


def _headers(settings: Settings) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
    }

    if settings.comfyui_api_key:
        headers["Authorization"] = (
            f"Bearer {settings.comfyui_api_key}"
        )

    if settings.comfyui_cf_access_client_id:
        headers["CF-Access-Client-Id"] = (
            settings.comfyui_cf_access_client_id
        )

    if settings.comfyui_cf_access_client_secret:
        headers["CF-Access-Client-Secret"] = (
            settings.comfyui_cf_access_client_secret
        )

    return headers


def _workflow(
    prompt: str,
    settings: Settings,
) -> dict[str, dict[str, Any]]:
    checkpoint = (settings.comfyui_checkpoint or "").strip()
    if not checkpoint:
        raise RuntimeError(
            "COMFYUI_CHECKPOINT configure nahi hai. "
            "ComfyUI models/checkpoints folder ka exact filename set karein."
        )

    width = max(512, min(1536, int(settings.comfyui_width)))
    height = max(512, min(1536, int(settings.comfyui_height)))
    steps = max(4, min(50, int(settings.comfyui_steps)))
    cfg = max(1.0, min(20.0, float(settings.comfyui_cfg)))

    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": random.randint(1, 2_147_483_647),
                "steps": steps,
                "cfg": cfg,
                "sampler_name": settings.comfyui_sampler_name,
                "scheduler": settings.comfyui_scheduler,
                "denoise": 1,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": checkpoint,
            },
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": 1,
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt[:4000],
                "clip": ["4", 1],
            },
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": settings.comfyui_negative_prompt[:2000],
                "clip": ["4", 1],
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2],
            },
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "VasukiAI",
                "images": ["8", 0],
            },
        },
    }


async def comfyui_health(settings: Settings) -> dict[str, Any]:
    base = _base_url(settings)
    if not base:
        return {
            "configured": False,
            "online": False,
            "detail": "COMFYUI_BASE_URL is not configured.",
        }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(12.0),
            follow_redirects=True,
        ) as client:
            response = await client.get(
                f"{base}/system_stats",
                headers=_headers(settings),
            )

        if response.is_error:
            return {
                "configured": True,
                "online": False,
                "status": response.status_code,
                "detail": (response.text or "")[:500],
            }

        return {
            "configured": True,
            "online": True,
            "checkpoint": settings.comfyui_checkpoint,
            "base_url": base,
        }
    except Exception as exc:
        return {
            "configured": True,
            "online": False,
            "detail": str(exc)[:500],
        }


def _history_entry(
    payload: Any,
    prompt_id: str,
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    entry = payload.get(prompt_id)
    if isinstance(entry, dict):
        return entry

    if "outputs" in payload:
        return payload

    return None


def _first_image(
    entry: dict[str, Any],
) -> dict[str, str] | None:
    outputs = entry.get("outputs")
    if not isinstance(outputs, dict):
        return None

    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        images = node_output.get("images")
        if not isinstance(images, list):
            continue

        for image in images:
            if not isinstance(image, dict):
                continue
            filename = str(image.get("filename") or "")
            if not filename:
                continue
            return {
                "filename": filename,
                "subfolder": str(image.get("subfolder") or ""),
                "type": str(image.get("type") or "output"),
            }

    return None


async def image_comfyui(
    prompt: str,
    settings: Settings,
) -> dict[str, str]:
    base = _base_url(settings)
    if not base:
        raise RuntimeError("COMFYUI_BASE_URL is not configured")

    workflow = _workflow(prompt, settings)
    client_id = str(uuid.uuid4())
    timeout_seconds = max(
        30,
        int(settings.comfyui_timeout_seconds),
    )

    timeout = httpx.Timeout(
        connect=20.0,
        read=45.0,
        write=45.0,
        pool=20.0,
    )

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        queued = await client.post(
            f"{base}/prompt",
            headers=_headers(settings),
            json={
                "prompt": workflow,
                "client_id": client_id,
            },
        )

        if queued.is_error:
            raise RuntimeError(
                "ComfyUI workflow queue fail hui: "
                f"HTTP {queued.status_code} "
                f"{(queued.text or '')[:700]}"
            )

        payload = queued.json()
        prompt_id = str(payload.get("prompt_id") or "")
        if not prompt_id:
            node_errors = payload.get("node_errors")
            raise RuntimeError(
                "ComfyUI ne prompt_id nahi diya. "
                f"Workflow error: {str(node_errors or payload)[:900]}"
            )

        deadline = asyncio.get_running_loop().time() + timeout_seconds

        while asyncio.get_running_loop().time() < deadline:
            history = await client.get(
                f"{base}/history/{quote(prompt_id)}",
                headers=_headers(settings),
            )

            if history.is_success:
                entry = _history_entry(history.json(), prompt_id)
                if entry:
                    image = _first_image(entry)
                    if image:
                        query = (
                            f"filename={quote(image['filename'])}"
                            f"&subfolder={quote(image['subfolder'])}"
                            f"&type={quote(image['type'])}"
                        )
                        output = await client.get(
                            f"{base}/view?{query}",
                            headers=_headers(settings),
                        )
                        if output.is_error:
                            raise RuntimeError(
                                "ComfyUI image download fail hui: "
                                f"HTTP {output.status_code}"
                            )

                        content_type = (
                            output.headers.get("content-type")
                            or "image/png"
                        ).split(";")[0]
                        encoded = base64.b64encode(
                            output.content
                        ).decode("ascii")

                        return {
                            "url": (
                                f"data:{content_type};base64,{encoded}"
                            ),
                            "provider": "comfyui-local",
                        }

                    status = entry.get("status")
                    if isinstance(status, dict):
                        messages = status.get("messages")
                        if status.get("completed") is True:
                            raise RuntimeError(
                                "ComfyUI workflow complete hui, "
                                "lekin output image nahi mili. "
                                f"{str(messages or '')[:600]}"
                            )

            await asyncio.sleep(1.0)

    raise RuntimeError(
        f"ComfyUI image generation {timeout_seconds} seconds me "
        "complete nahi hui."
    )
