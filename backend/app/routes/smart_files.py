from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.auth import AuthUser, get_current_user
from app.config import get_settings
from app.services.file_artifacts import process_smart_file_request


router = APIRouter(tags=["smart-files"])
settings = get_settings()


@router.post("/api/smart-files")
async def smart_files(
    prompt: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    _current_user: AuthUser = Depends(get_current_user),
) -> dict:
    clean_prompt = prompt.strip()
    if not clean_prompt:
        raise HTTPException(status_code=400, detail="Write an instruction or question first.")

    if len(clean_prompt) > 12_000:
        raise HTTPException(status_code=400, detail="Instruction must be 12,000 characters or shorter.")

    if len(files) > 8:
        raise HTTPException(status_code=400, detail="Upload up to 8 files at a time.")

    uploads: list[dict[str, object]] = []
    total_bytes = 0
    for upload in files:
        content = await upload.read()
        total_bytes += len(content)
        uploads.append(
            {
                "filename": upload.filename or "document",
                "mime_type": upload.content_type or "application/octet-stream",
                "content": content,
            }
        )

    if total_bytes > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Combined upload size must be 50 MB or smaller.")

    try:
        return await process_smart_file_request(
            uploads=uploads,
            prompt=clean_prompt,
            settings=settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        detail = str(exc).strip()[:1200]
        raise HTTPException(
            status_code=503,
            detail=detail or "Smart file processing failed. Please retry.",
        ) from exc
