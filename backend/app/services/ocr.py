from __future__ import annotations
import httpx
from fastapi import UploadFile
from app.config import Settings


async def extract_text(file: UploadFile, settings: Settings) -> dict:
    if not settings.ocr_space_api:
        raise RuntimeError("OCR_SPACE_API is not configured")
    content = await file.read()
    files = {"file": (file.filename or "upload.png", content, file.content_type or "application/octet-stream")}
    data = {"apikey": settings.ocr_space_api, "language": "eng", "isOverlayRequired": "false"}
    async with httpx.AsyncClient(timeout=max(settings.request_timeout_seconds, 120)) as client:
        response = await client.post("https://api.ocr.space/parse/image", data=data, files=files)
        response.raise_for_status()
        payload = response.json()
    text = "\n".join(item.get("ParsedText", "") for item in payload.get("ParsedResults", []))
    return {"text": text.strip(), "provider": "ocr.space", "raw_error": payload.get("ErrorMessage")}
