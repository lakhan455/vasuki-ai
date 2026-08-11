from __future__ import annotations
from typing import Any
import httpx

def _key(settings) -> str:
    return str(getattr(settings, "supabase_service_role_key", None) or getattr(settings, "supabase_secret_key", None) or "").strip()

def configured(settings) -> bool:
    return bool(str(getattr(settings, "supabase_url", "") or "").strip() and _key(settings))

def headers(settings) -> dict[str, str]:
    key = _key(settings)
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Prefer": "return=representation"}

async def request(settings, method: str, path: str, *, params: dict[str, Any] | None = None, json_body: Any = None, timeout: float = 12.0) -> Any:
    if not configured(settings):
        return None
    url = f"{str(settings.supabase_url).rstrip('/')}/rest/v1/{path.lstrip('/')}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(method.upper(), url, headers=headers(settings), params=params, json=json_body)
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase V11 store failed ({response.status_code}): {response.text[:500]}")
    if not response.content:
        return None
    try:
        return response.json()
    except Exception:
        return response.text

async def rpc(settings, name: str, payload: dict[str, Any] | None = None) -> Any:
    if not configured(settings):
        return None
    url = f"{str(settings.supabase_url).rstrip('/')}/rest/v1/rpc/{name}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, headers=headers(settings), json=payload or {})
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase RPC {name} failed ({response.status_code}): {response.text[:500]}")
    try:
        return response.json()
    except Exception:
        return None
