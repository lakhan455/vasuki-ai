from __future__ import annotations

import asyncio
import io
import math
import re
import uuid
from typing import Any
from urllib.parse import quote

import httpx
from docx import Document as DocxDocument
from pypdf import PdfReader

from app.config import Settings


ALLOWED_DOCUMENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
}

ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def _server_key(settings: Settings) -> str:
    return (
        settings.supabase_secret_key
        or settings.supabase_service_role_key
        or ""
    )


def _headers(settings: Settings, *, representation: bool = False) -> dict[str, str]:
    key = _server_key(settings)
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
    }
    if key and not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    if representation:
        headers["Prefer"] = "return=representation"
    return headers


def _base_url(settings: Settings) -> str:
    return (settings.supabase_url or "").rstrip("/")


def _configured(settings: Settings) -> bool:
    return bool(
        _base_url(settings)
        and _server_key(settings)
        and settings.google_gemini_api
    )


def _clean_text(value: str) -> str:
    value = value.replace("\x00", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _safe_document_ids(values: list[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        try:
            result.append(str(uuid.UUID(str(value))))
        except (ValueError, TypeError):
            continue
    return result[:50]


def extract_document_pages(
    content: bytes,
    filename: str,
    mime_type: str,
) -> list[tuple[int | None, str]]:
    suffix = "." + filename.rsplit(".", 1)[-1].casefold() if "." in filename else ""

    if mime_type == "application/pdf" or suffix == ".pdf":
        reader = PdfReader(io.BytesIO(content))
        pages: list[tuple[int | None, str]] = []
        for index, page in enumerate(reader.pages[:300], 1):
            text = _clean_text(page.extract_text() or "")
            if text:
                pages.append((index, text))
        return pages

    if (
        mime_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        or suffix == ".docx"
    ):
        document = DocxDocument(io.BytesIO(content))
        text = _clean_text("\n".join(
            paragraph.text for paragraph in document.paragraphs
        ))
        return [(None, text)] if text else []

    if mime_type in {"text/plain", "text/markdown"} or suffix in {".txt", ".md"}:
        text = content.decode("utf-8", errors="replace")
        text = _clean_text(text)
        return [(None, text)] if text else []

    raise ValueError("Only PDF, DOCX, TXT and MD documents are supported.")


def chunk_document(
    pages: list[tuple[int | None, str]],
    *,
    chunk_size: int = 1800,
    overlap: int = 240,
    max_chunks: int = 120,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []

    for page_number, page_text in pages:
        text = _clean_text(page_text)
        if not text:
            continue

        start = 0
        while start < len(text) and len(chunks) < max_chunks:
            end = min(len(text), start + chunk_size)
            if end < len(text):
                boundary = max(
                    text.rfind("\n", start + chunk_size // 2, end),
                    text.rfind(". ", start + chunk_size // 2, end),
                    text.rfind(" ", start + chunk_size // 2, end),
                )
                if boundary > start:
                    end = boundary + 1

            piece = _clean_text(text[start:end])
            if piece:
                chunks.append(
                    {
                        "chunk_index": len(chunks),
                        "page_number": page_number,
                        "content": piece,
                    }
                )

            if end >= len(text):
                break
            start = max(start + 1, end - overlap)

        if len(chunks) >= max_chunks:
            break

    return chunks


async def _embed_batch(
    texts: list[str],
    settings: Settings,
    *,
    task_type: str,
    title: str | None = None,
) -> list[list[float]]:
    if not settings.google_gemini_api:
        raise RuntimeError("GOOGLE_GEMINI_API is not configured.")

    model = settings.gemini_embedding_model
    model_name = f"models/{model}"
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"{model_name}:batchEmbedContents"
    )

    results: list[list[float]] = []
    batch_size = 20

    async with httpx.AsyncClient(timeout=45.0) as client:
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            requests: list[dict[str, Any]] = []

            for text in batch:
                item: dict[str, Any] = {
                    "model": model_name,
                    "content": {"parts": [{"text": text}]},
                    "taskType": task_type,
                    "outputDimensionality": settings.embedding_dimensions,
                }
                if title and task_type == "RETRIEVAL_DOCUMENT":
                    item["title"] = title[:200]
                requests.append(item)

            response = await client.post(
                url,
                headers={"x-goog-api-key": settings.google_gemini_api},
                json={"requests": requests},
            )
            if response.is_error:
                detail = response.text[:800]
                raise RuntimeError(
                    f"Embedding API failed ({response.status_code}): {detail}"
                )

            payload = response.json()
            embeddings = payload.get("embeddings") or []
            if len(embeddings) != len(batch):
                raise RuntimeError("Embedding API returned an incomplete batch.")

            for embedding in embeddings:
                values = embedding.get("values") or []
                vector = [float(value) for value in values]
                if len(vector) != settings.embedding_dimensions:
                    raise RuntimeError(
                        "Embedding dimension does not match database schema."
                    )
                results.append(vector)

    return results


async def embed_query(query: str, settings: Settings) -> list[float]:
    vectors = await _embed_batch(
        [query[:12000]],
        settings,
        task_type="RETRIEVAL_QUERY",
    )
    return vectors[0]


async def list_user_documents(
    user_id: str,
    settings: Settings,
) -> list[dict[str, Any]]:
    if not _base_url(settings) or not _server_key(settings):
        return []

    url = (
        f"{_base_url(settings)}/rest/v1/user_documents"
        f"?user_id=eq.{quote(user_id)}"
        "&select=id,name,mime_type,size_bytes,status,chunk_count,created_at,updated_at"
        "&order=created_at.desc"
    )
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(url, headers=_headers(settings))
        response.raise_for_status()
        rows = response.json()
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


async def _update_document(
    document_id: str,
    user_id: str,
    settings: Settings,
    values: dict[str, Any],
) -> None:
    url = (
        f"{_base_url(settings)}/rest/v1/user_documents"
        f"?id=eq.{quote(document_id)}&user_id=eq.{quote(user_id)}"
    )
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.patch(
            url,
            headers=_headers(settings),
            json=values,
        )
    response.raise_for_status()


async def ingest_user_document(
    *,
    user_id: str,
    filename: str,
    mime_type: str,
    content: bytes,
    settings: Settings,
) -> dict[str, Any]:
    if not _configured(settings):
        raise RuntimeError(
            "Supabase server credentials and GOOGLE_GEMINI_API are required."
        )

    max_bytes = int(settings.document_max_mb) * 1024 * 1024
    if len(content) > max_bytes:
        raise ValueError(
            f"Document must be {settings.document_max_mb} MB or smaller."
        )

    suffix = "." + filename.rsplit(".", 1)[-1].casefold() if "." in filename else ""
    if mime_type not in ALLOWED_DOCUMENT_TYPES and suffix not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise ValueError("Only PDF, DOCX, TXT and MD documents are supported.")

    pages = extract_document_pages(content, filename, mime_type)
    if not pages:
        raise ValueError(
            "No readable text was found. Scanned PDFs should be OCR-processed first."
        )

    chunks = chunk_document(
        pages,
        max_chunks=settings.document_max_chunks,
    )
    if not chunks:
        raise ValueError("The document did not contain usable text.")

    create_url = f"{_base_url(settings)}/rest/v1/user_documents"
    create_payload = {
        "user_id": user_id,
        "name": filename[:240],
        "mime_type": mime_type[:120],
        "size_bytes": len(content),
        "status": "processing",
        "chunk_count": 0,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            create_url,
            headers=_headers(settings, representation=True),
            json=create_payload,
        )
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("Document record could not be created.")

    document = rows[0]
    document_id = str(document["id"])

    try:
        vectors = await _embed_batch(
            [item["content"] for item in chunks],
            settings,
            task_type="RETRIEVAL_DOCUMENT",
            title=filename,
        )

        chunk_rows = []
        for item, vector in zip(chunks, vectors, strict=True):
            chunk_rows.append(
                {
                    "user_id": user_id,
                    "document_id": document_id,
                    "chunk_index": item["chunk_index"],
                    "page_number": item["page_number"],
                    "content": item["content"],
                    "embedding": vector,
                    "metadata": {"filename": filename},
                }
            )

        insert_url = f"{_base_url(settings)}/rest/v1/user_document_chunks"
        async with httpx.AsyncClient(timeout=30.0) as client:
            for start in range(0, len(chunk_rows), 40):
                response = await client.post(
                    insert_url,
                    headers=_headers(settings),
                    json=chunk_rows[start:start + 40],
                )
                response.raise_for_status()

        await _update_document(
            document_id,
            user_id,
            settings,
            {"status": "ready", "chunk_count": len(chunk_rows)},
        )
    except Exception:
        try:
            await _update_document(
                document_id,
                user_id,
                settings,
                {"status": "failed"},
            )
        except Exception:
            pass
        raise

    return {
        **document,
        "status": "ready",
        "chunk_count": len(chunks),
    }


async def delete_user_document(
    user_id: str,
    document_id: str,
    settings: Settings,
) -> None:
    safe_id = str(uuid.UUID(document_id))
    url = (
        f"{_base_url(settings)}/rest/v1/user_documents"
        f"?id=eq.{quote(safe_id)}&user_id=eq.{quote(user_id)}"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.delete(url, headers=_headers(settings))
    response.raise_for_status()


async def search_user_documents(
    *,
    user_id: str,
    query: str,
    document_ids: list[str] | None,
    settings: Settings,
    match_count: int = 8,
) -> list[dict[str, Any]]:
    if not _configured(settings):
        return []

    safe_ids = _safe_document_ids(document_ids)
    vector = await embed_query(query, settings)

    url = (
        f"{_base_url(settings)}/rest/v1/rpc/"
        "match_user_document_chunks"
    )
    payload = {
        "p_user_id": user_id,
        "p_query_embedding": vector,
        "p_match_count": max(1, min(match_count, 15)),
        "p_document_ids": safe_ids or None,
    }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(
                url,
                headers=_headers(settings),
                json=payload,
            )
        response.raise_for_status()
        rows = response.json()
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def document_context(
    hits: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    if not hits:
        return "", []

    context_parts = [
        "PRIVATE DOCUMENT KNOWLEDGE:",
        "Answer from these retrieved document passages when relevant. "
        "Cite them inline as [DOC 1], [DOC 2], etc. "
        "Do not invent content outside the retrieved passages.",
    ]
    sources: list[dict[str, Any]] = []

    for index, hit in enumerate(hits, 1):
        name = str(hit.get("document_name") or "Document")
        page = hit.get("page_number")
        page_label = f"Page {page}" if page else "Page not available"
        content = str(hit.get("content") or "").strip()
        context_parts.append(
            f"[DOC {index}]\n"
            f"DOCUMENT: {name}\n"
            f"{page_label}\n"
            f"CONTENT:\n{content}"
        )
        sources.append(
            {
                "title": f"{name} · {page_label}",
                "url": "",
                "domain": "Your document",
                "source_type": "document",
                "document_id": str(hit.get("document_id") or ""),
                "page_number": page,
                "content": content[:1000],
            }
        )

    return "\n\n".join(context_parts), sources
