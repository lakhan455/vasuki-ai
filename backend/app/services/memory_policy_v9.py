from __future__ import annotations
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
import httpx
from app.config import Settings
from app.services import personal_memory as legacy
from app.services.memory_v8 import create_user_memory_v8, normalize_memory_text, _embed_memory

LIFETIMES = {
    "personal_preference": 3650,
    "project_fact": 3650,
    "temporary_context": 7,
    "instruction": 3650,
    "technical_configuration": 365,
}

def classify_memory(text: str, requested: str | None = None) -> str:
    value = str(requested or "").lower().strip().replace(" ", "_")
    value = {"preference":"personal_preference","project":"project_fact","temporary":"temporary_context","config":"technical_configuration","configuration":"technical_configuration"}.get(value, value)
    if value in LIFETIMES:
        return value
    low = text.casefold()
    if any(x in low for x in ("prefer", "pasand", "favorite", "favourite")):
        return "personal_preference"
    if any(x in low for x in ("must ", "should ", "always ", "hamesha", "instruction")):
        return "instruction"
    if any(x in low for x in ("backend", "frontend", "database", "api", "model", "version", "port", "url")):
        return "technical_configuration"
    if any(x in low for x in ("project", "app", "website", "repo")):
        return "project_fact"
    return "temporary_context"

def subject_key(text: str, category: str) -> str:
    low = normalize_memory_text(text)
    low = re.sub(r"\bv?\d+(?:\.\d+){0,3}\b", "<version>", low)
    low = re.sub(r"https?://\S+", "<url>", low)
    words = re.findall(r"[\w-]+", low)
    stop = {"the","a","an","is","are","will","should","use","uses","hai","he","ka","ki","ke","par","pe","me","mein"}
    return category + ":" + " ".join([w for w in words if w not in stop][:9])

def _expires(category: str):
    days = LIFETIMES.get(category, 7)
    if days >= 3650:
        return None
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

async def create_user_memory_v9(user_id: str, memory_text: str, settings: Settings, *, category: str = "preference", user_jwt: str | None = None, source: str = "explicit", confidence: float = 1.0):
    cleaned = legacy.clean_memory_text(memory_text)
    if len(cleaned) < 3:
        raise ValueError("Memory must contain at least 3 characters.")
    if legacy._contains_private_data(cleaned):
        raise ValueError("Sensitive information cannot be saved as memory.")
    memory_type = classify_memory(cleaned, category)
    key = subject_key(cleaned, memory_type)
    embedding = await _embed_memory(cleaned, settings)
    payload = {
        "user_id": user_id,
        "memory_text": cleaned,
        "category": memory_type,
        "confidence": max(0.0, min(float(confidence), 1.0)),
        "source": str(source or "explicit")[:40],
        "normalized_text": normalize_memory_text(cleaned),
        "memory_type": memory_type,
        "subject_key": key,
        "status": "active",
        "expires_at": _expires(memory_type),
    }
    if embedding is not None:
        payload["embedding"] = embedding
    base = legacy._base_url(settings)
    headers = legacy._headers(settings, representation=True, user_jwt=user_jwt)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"{base}/rest/v1/user_memories", headers=headers, json=payload)
    if response.status_code in {400, 404} and ("column" in response.text.casefold() or "schema cache" in response.text.casefold()):
        return await create_user_memory_v8(user_id, cleaned, settings, category=memory_type, user_jwt=user_jwt, source=source, confidence=confidence)
    response.raise_for_status()
    rows = response.json()
    created = rows[0] if isinstance(rows, list) and rows else payload
    new_id = str(created.get("id") or "")
    if new_id:
        q = f"{base}/rest/v1/user_memories?user_id=eq.{quote(user_id)}&subject_key=eq.{quote(key)}&status=eq.active&id=neq.{quote(new_id)}"
        async with httpx.AsyncClient(timeout=8.0) as client:
            await client.patch(q, headers=legacy._headers(settings, user_jwt=user_jwt), json={"status":"superseded","superseded_by":new_id})
    return created

def policy_summary():
    return {"categories": LIFETIMES, "conflict_resolution":"same subject_key supersedes older active memory"}
