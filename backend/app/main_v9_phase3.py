from __future__ import annotations

import base64
from typing import Any

from fastapi import Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

import app.main_v9_phase2 as phase2
from app.auth import AuthUser, get_current_user
from app.services.artifacts_v8 import save_artifact
from app.services.document_intelligence_v9 import (
    answer_with_citations,
    compare_with_citations,
    extract_uploads,
)
from app.services.image_quota_guard import (
    quota_payload,
    release_image_slots,
    reserve_image_slots,
)
from app.services.image_studio_v9 import (
    ASPECT_RATIOS,
    IMAGE_PRESETS,
    edit_studio_image,
    generate_studio_image,
    generate_variations,
    normalize_aspect_ratio,
    normalize_preset,
    upscale_image_bytes,
)
from app.services.plans_v2 import get_plan_status

app = phase2.app
settings = phase2.settings


class ImageStudioRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=5000)
    preset: str = Field(default="none", max_length=40)
    aspect_ratio: str = Field(default="square", max_length=40)


class ImageVariationRequest(ImageStudioRequest):
    count: int = Field(default=4, ge=2, le=4)


async def _store_image(
    *,
    current_user: AuthUser,
    result: dict[str, Any],
    prompt: str,
    name: str,
) -> dict[str, Any] | None:
    url = str(result.get("url") or "")
    if not url:
        return None
    status = await get_plan_status(current_user, settings)
    mime = "image/png" if url.startswith("data:image/png") else "image/jpeg"
    return await save_artifact(
        settings,
        user_id=current_user.id,
        name=name,
        artifact_type="image",
        mime_type=mime,
        data_url=url if url.startswith("data:") else None,
        external_url=url if url.startswith("http") else None,
        prompt=prompt,
        provider=str(result.get("provider") or ""),
        retention_days=30 if status.plan in {"owner", "pro"} else 15,
    )


@app.get("/api/image/v3/options")
async def image_studio_options(
    _current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "presets": list(IMAGE_PRESETS.keys()),
        "aspect_ratios": {
            key: {"width": value[0], "height": value[1]}
            for key, value in ASPECT_RATIOS.items()
        },
        "max_variations": 4,
        "local_enhance_max_scale": 4,
    }


@app.post("/api/image/v3/generate")
async def image_studio_generate(
    payload: ImageStudioRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    reserved, quota = await reserve_image_slots(
        current_user.id,
        settings,
        count=1,
    )

    try:
        result = await generate_studio_image(
            settings,
            prompt=payload.prompt,
            preset=payload.preset,
            aspect_ratio=payload.aspect_ratio,
        )
        artifact = await _store_image(
            current_user=current_user,
            result=result,
            prompt=payload.prompt,
            name=f"Vasuki {normalize_preset(payload.preset)} image",
        )
        return {
            "ok": True,
            **result,
            "artifact": artifact,
            "image_quota": quota_payload(quota),
        }

    except ValueError as exc:
        await release_image_slots(
            current_user.id,
            settings,
            count=reserved,
        )

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except HTTPException:
        await release_image_slots(
            current_user.id,
            settings,
            count=reserved,
        )
        raise

    except Exception as exc:
        await release_image_slots(
            current_user.id,
            settings,
            count=reserved,
        )

        raise HTTPException(
            status_code=503,
            detail=str(exc)[:1400],
        ) from exc


@app.post("/api/image/v3/variations")
async def image_studio_variations(
    payload: ImageVariationRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    reserved, quota = await reserve_image_slots(
        current_user.id,
        settings,
        count=payload.count,
    )

    try:
        result = await generate_variations(
            settings,
            prompt=payload.prompt,
            preset=payload.preset,
            aspect_ratio=payload.aspect_ratio,
            count=payload.count,
        )
        for item in result["items"]:
            if item.get("ok") and item.get("url"):
                item["artifact"] = await _store_image(
                    current_user=current_user,
                    result=item,
                    prompt=payload.prompt,
                    name=f"Vasuki variation {item.get('index')}",
                )
        succeeded = max(
            0,
            min(
                reserved,
                int(result.get("succeeded") or 0),
            ),
        )

        unused = reserved - succeeded

        if unused:
            released_quota = await release_image_slots(
                current_user.id,
                settings,
                count=unused,
            )

            if released_quota is not None:
                quota = released_quota

        return {
            "ok": succeeded > 0,
            **result,
            "image_quota": quota_payload(quota),
        }

    except ValueError as exc:
        await release_image_slots(
            current_user.id,
            settings,
            count=reserved,
        )

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except HTTPException:
        await release_image_slots(
            current_user.id,
            settings,
            count=reserved,
        )
        raise

    except Exception as exc:
        await release_image_slots(
            current_user.id,
            settings,
            count=reserved,
        )

        raise HTTPException(
            status_code=503,
            detail=str(exc)[:1400],
        ) from exc


@app.post("/api/image/v3/edit")
async def image_studio_edit(
    file: UploadFile = File(...),
    prompt: str = Form(...),
    preset: str = Form("none"),
    aspect_ratio: str = Form("square"),
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    content = await file.read()
    if not content or len(content) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Upload an image up to 15 MB.")
    mime = (file.content_type or "").split(";", 1)[0].casefold()
    if not mime.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Image Edit accepts image files only.",
        )

    reserved, quota = await reserve_image_slots(
        current_user.id,
        settings,
        count=1,
    )

    try:
        result = await edit_studio_image(
            settings,
            content=content,
            filename=file.filename or "image.png",
            mime_type=mime,
            prompt=prompt,
            preset=preset,
            aspect_ratio=aspect_ratio,
        )
        artifact = await _store_image(
            current_user=current_user,
            result=result,
            prompt=prompt,
            name="Vasuki edited image",
        )
        return {
            "ok": True,
            **result,
            "artifact": artifact,
            "image_quota": quota_payload(quota),
        }

    except HTTPException:
        await release_image_slots(
            current_user.id,
            settings,
            count=reserved,
        )
        raise

    except Exception as exc:
        await release_image_slots(
            current_user.id,
            settings,
            count=reserved,
        )

        raise HTTPException(
            status_code=503,
            detail=str(exc)[:1400],
        ) from exc


@app.post("/api/image/v3/enhance")
async def image_studio_enhance(
    file: UploadFile = File(...),
    scale: float = Form(2.0),
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    content = await file.read()
    if not content or len(content) > 15 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="Upload an image up to 15 MB.",
        )

    reserved, quota = await reserve_image_slots(
        current_user.id,
        settings,
        count=1,
    )

    try:
        output, metadata = upscale_image_bytes(content, scale=scale)
        url = "data:image/png;base64," + base64.b64encode(output).decode("ascii")
        result = {
            "url": url,
            "provider": "vasuki-local-enhancer-v9",
            "operation": "enhance",
            **metadata,
        }
        artifact = await _store_image(
            current_user=current_user,
            result=result,
            prompt=f"Local enhance x{metadata['requested_scale']}",
            name="Vasuki enhanced image",
        )
        return {"ok": True, **result, "artifact": artifact}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)[:1400]) from exc


async def _uploads(files: list[UploadFile]) -> list[dict[str, Any]]:
    if not files or len(files) > 8:
        raise HTTPException(status_code=400, detail="Upload between 1 and 8 documents.")
    rows = []
    total = 0
    for upload in files:
        content = await upload.read()
        total += len(content)
        if len(content) > 15 * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"{upload.filename}: file is larger than 15 MB.")
        rows.append({
            "filename": upload.filename or "document",
            "mime_type": upload.content_type or "application/octet-stream",
            "content": content,
        })
    if total > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Combined document upload must be 50 MB or smaller.")
    return rows


@app.post("/api/documents/v3/extract")
async def document_v3_extract(
    files: list[UploadFile] = File(default=[]),
    _current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        extracted = await extract_uploads(await _uploads(files), settings=settings)
        return {"ok": True, **extracted}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:1600]) from exc


@app.post("/api/documents/v3/ocr")
async def document_v3_ocr(
    file: UploadFile = File(...),
    _current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        extracted = await extract_uploads(await _uploads([file]), settings=settings)
        document = extracted["documents"][0]
        text = "\n\n".join(str(item.get("text") or "") for item in document.get("blocks") or [])
        return {
            "ok": True,
            "text": text,
            "document": document,
            "warnings": extracted.get("warnings") or [],
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:1600]) from exc


@app.post("/api/documents/v3/ask")
async def document_v3_ask(
    prompt: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    _current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="Write a document question first.")
    try:
        extracted = await extract_uploads(await _uploads(files), settings=settings)
        answer = await answer_with_citations(
            prompt=prompt,
            documents=extracted["documents"],
            settings=settings,
        )
        return {
            "ok": True,
            **answer,
            "documents": extracted["documents"],
            "warnings": extracted.get("warnings") or [],
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:1600]) from exc


@app.post("/api/documents/v3/compare")
async def document_v3_compare(
    prompt: str = Form("Compare these documents."),
    files: list[UploadFile] = File(default=[]),
    _current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="Upload at least two documents to compare.")
    try:
        extracted = await extract_uploads(await _uploads(files), settings=settings)
        answer = await compare_with_citations(
            prompt=prompt,
            documents=extracted["documents"],
            settings=settings,
        )
        return {
            "ok": True,
            **answer,
            "documents": extracted["documents"],
            "warnings": extracted.get("warnings") or [],
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:1600]) from exc


@app.get("/health/v9-phase3")
async def health_v9_phase3() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v9-phase3",
        "image_presets": True,
        "aspect_ratio_controls": True,
        "image_variations": True,
        "image_edit_ui_api": True,
        "image_upscale_enhance": True,
        "ocr_v2": True,
        "structured_document_extraction": True,
        "document_page_section_citations": True,
        "document_compare": True,
        "upscale_note": "Enhancement uses local high-quality resampling and sharpening; it is not generative super-resolution.",
        "citation_note": "Native PDF citations are page-level; DOCX/TXT citations are section/line-level. Vision OCR fallback may not have reliable page boundaries.",
    }
