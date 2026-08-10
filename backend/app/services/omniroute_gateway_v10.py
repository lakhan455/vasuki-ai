from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from collections import deque
from typing import Any, AsyncIterator
from urllib.parse import urlparse

import httpx

from app.config import Settings


class OmniRouteError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retry_after: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


_RECENT: deque[dict[str, Any]] = deque(maxlen=80)
_STATS: dict[str, Any] = {
    "requests": 0,
    "successes": 0,
    "failures": 0,
    "fallbacks": 0,
    "last_success_at": None,
    "last_failure_at": None,
    "last_error": "",
    "last_model": "",
    "last_provider": "",
    "last_decision": "",
    "last_latency_ms": None,
}

def _now() -> float:
    return time.time()

def _api_base(settings: Settings) -> str:
    raw = str(getattr(settings, "omniroute_base_url", "") or "").strip().rstrip("/")
    if not raw:
        return ""
    return raw if raw.endswith("/v1") else raw + "/v1"

def _origin(settings: Settings) -> str:
    base = _api_base(settings)
    return base[:-3] if base.endswith("/v1") else base

def configured(settings: Settings) -> bool:
    return bool(getattr(settings, "omniroute_enabled", False) and _api_base(settings))

def _auth_headers(settings: Settings) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    key = str(getattr(settings, "omniroute_api_key", "") or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers

def _safe_error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            detail = payload.get("error") or payload.get("detail") or payload.get("message") or payload
            return str(detail)[:1200]
    except Exception:
        pass
    return (response.text or f"HTTP {response.status_code}")[:1200]

def _session_id(messages: list[dict[str, Any]]) -> str:
    seed = next(
        (
            str(item.get("content") or "").strip()
            for item in messages
            if str(item.get("role") or "") == "user" and str(item.get("content") or "").strip()
        ),
        "",
    )
    if not seed:
        seed = "vasuki-session"
    digest = hashlib.sha256(seed[:4000].encode("utf-8", errors="ignore")).hexdigest()[:24]
    return f"vasuki-{digest}"

def route_profile(task_type: str, *, require_current: bool = False) -> tuple[str, str]:
    task = (task_type or "general").casefold()
    if task == "code":
        return "auto/coding:reliable", "reliable"
    if task == "reasoning":
        return "auto/reasoning:reliable", "quality"
    if task == "research" or require_current:
        return "auto/reasoning:reliable", "reliable"
    if task == "simple":
        return "auto/fast", "fast"
    return "auto", "balanced"

def _headers_for_request(
    settings: Settings,
    *,
    mode: str,
    request_id: str,
    cache_bypass: bool,
) -> dict[str, str]:
    headers = _auth_headers(settings)
    headers["X-Request-Id"] = request_id
    headers["X-OmniRoute-Mode"] = mode
    # Vasuki already owns user memory. Avoid duplicate memory/skills injection inside the gateway.
    headers["x-omniroute-no-memory"] = "true"
    if cache_bypass:
        headers["X-OmniRoute-No-Cache"] = "true"

    compression = str(getattr(settings, "omniroute_compression", "default") or "default").strip()
    if compression:
        headers["x-omniroute-compression"] = compression

    budget = float(getattr(settings, "omniroute_budget_usd", 0.0) or 0.0)
    if budget > 0:
        headers["X-OmniRoute-Budget"] = f"{budget:.8f}".rstrip("0").rstrip(".")
        fallback = str(getattr(settings, "omniroute_budget_fallback", "cheapest") or "cheapest").strip()
        headers["X-OmniRoute-Budget-Fallback"] = fallback if fallback in {"strict", "cheapest"} else "cheapest"

    return headers

def _context_messages(messages: list[dict[str, Any]], web_context: str) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    context = (web_context or "").strip()
    if context:
        output.append({
            "role": "system",
            "content": (
                "VASUKI TRUSTED CONTEXT:\n"
                "Use the supplied context as evidence/context for this request. "
                "Do not invent citations or claims not supported by it when the request requires verification.\n\n"
                + context
            ),
        })
    for item in messages:
        role = str(item.get("role") or "user")
        content = str(item.get("content") or "").strip()
        if content:
            output.append({"role": role, "content": content})
    return output

def _extract_delta_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    choice = choices[0] if isinstance(choices[0], dict) else {}
    delta = choice.get("delta") if isinstance(choice, dict) else None
    if isinstance(delta, dict):
        content = delta.get("content")
    else:
        content = choice.get("text") if isinstance(choice, dict) else ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if isinstance(value, str):
                    parts.append(value)
        return "".join(parts)
    return ""

def _record(event: dict[str, Any]) -> None:
    _RECENT.appendleft(event)

def mark_fallback(reason: str) -> None:
    _STATS["fallbacks"] = int(_STATS.get("fallbacks") or 0) + 1
    _record({"time": _now(), "event": "fallback", "reason": reason[:300]})

def snapshot() -> dict[str, Any]:
    return {**_STATS, "recent": list(_RECENT)[:25]}

async def stream_chat(
    messages: list[dict[str, Any]],
    settings: Settings,
    web_context: str = "",
    *,
    task_type: str = "general",
    require_current: bool = False,
    cache_bypass: bool = False,
) -> AsyncIterator[dict[str, str]]:
    if not configured(settings):
        raise OmniRouteError("OmniRoute gateway is not configured.")

    model, mode = route_profile(task_type, require_current=require_current)
    request_id = str(uuid.uuid4())
    headers = _headers_for_request(settings, mode=mode, request_id=request_id, cache_bypass=cache_bypass)
    session_id = _session_id(messages)
    headers["X-Session-Id"] = session_id
    headers["X-OmniRoute-Session-Id"] = session_id
    payload = {
        "model": model,
        "messages": _context_messages(messages, web_context),
        "stream": True,
    }

    timeout_seconds = max(10.0, float(getattr(settings, "omniroute_timeout_seconds", 65) or 65))
    timeout = httpx.Timeout(connect=12.0, read=timeout_seconds, write=30.0, pool=12.0)
    url = _api_base(settings) + "/chat/completions"
    started = time.perf_counter()
    _STATS["requests"] = int(_STATS.get("requests") or 0) + 1
    emitted = False

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.is_error:
                    retry_after = response.headers.get("retry-after")
                    raise OmniRouteError(
                        f"OmniRoute HTTP {response.status_code}: {_safe_error_text(response)}",
                        status_code=response.status_code,
                        retry_after=retry_after,
                    )

                upstream_provider = response.headers.get("X-OmniRoute-Provider") or ""
                upstream_model = response.headers.get("X-OmniRoute-Model") or model
                decision = response.headers.get("X-OmniRoute-Decision") or ""
                provider_label = "omniroute"
                if upstream_provider:
                    provider_label += f":{upstream_provider}"
                if upstream_model:
                    provider_label += f"/{upstream_model}"

                _STATS["last_model"] = upstream_model
                _STATS["last_provider"] = upstream_provider
                _STATS["last_decision"] = decision

                buffer = ""
                async for raw in response.aiter_text():
                    if not raw:
                        continue
                    buffer += raw
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line or line.startswith(":"):
                            continue
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(event, dict):
                            continue
                        token = _extract_delta_content(event)
                        if token:
                            if not emitted:
                                emitted = True
                                yield {"type": "provider", "provider": provider_label}
                                yield {
                                    "type": "diagnostic",
                                    "provider": provider_label,
                                    "status": f"omniroute:{mode}:{model}",
                                }
                            yield {"type": "token", "token": token}

                # Handle a final line without newline.
                tail = buffer.strip()
                if tail.startswith("data:"):
                    data = tail[5:].strip()
                    if data and data != "[DONE]":
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            event = {}
                        if isinstance(event, dict):
                            token = _extract_delta_content(event)
                            if token:
                                if not emitted:
                                    emitted = True
                                    yield {"type": "provider", "provider": provider_label}
                                yield {"type": "token", "token": token}

        if not emitted:
            raise OmniRouteError("OmniRoute returned an empty stream.")

        latency = round((time.perf_counter() - started) * 1000, 1)
        _STATS["successes"] = int(_STATS.get("successes") or 0) + 1
        _STATS["last_success_at"] = _now()
        _STATS["last_latency_ms"] = latency
        _STATS["last_error"] = ""
        _record({
            "time": _now(),
            "event": "success",
            "model": model,
            "mode": mode,
            "provider": _STATS.get("last_provider") or "",
            "latency_ms": latency,
        })
    except Exception as exc:
        latency = round((time.perf_counter() - started) * 1000, 1)
        _STATS["failures"] = int(_STATS.get("failures") or 0) + 1
        _STATS["last_failure_at"] = _now()
        _STATS["last_latency_ms"] = latency
        _STATS["last_error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
        _record({"time": _now(), "event": "failure", "error": _STATS["last_error"], "latency_ms": latency})
        raise

async def generate_image(prompt: str, settings: Settings, *, size: str = "1024x1024") -> dict[str, Any]:
    if not configured(settings):
        raise OmniRouteError("OmniRoute gateway is not configured.")
    model = str(getattr(settings, "omniroute_image_model", "") or "").strip()
    if not model:
        raise OmniRouteError("OMNIROUTE_IMAGE_MODEL is not configured.")

    headers = _headers_for_request(
        settings,
        mode="quality",
        request_id=str(uuid.uuid4()),
        cache_bypass=True,
    )
    payload = {"model": model, "prompt": prompt, "size": size}
    url = _api_base(settings) + "/images/generations"
    timeout_seconds = max(30.0, float(getattr(settings, "total_image_timeout_seconds", 150) or 150))

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(url, headers=headers, json=payload)
    if response.is_error:
        raise OmniRouteError(
            f"OmniRoute image HTTP {response.status_code}: {_safe_error_text(response)}",
            status_code=response.status_code,
            retry_after=response.headers.get("retry-after"),
        )

    payload = response.json()
    data = payload.get("data") or []
    item = data[0] if data and isinstance(data[0], dict) else {}
    url_value = item.get("url")
    if isinstance(url_value, str) and url_value.strip():
        return {"url": url_value.strip(), "provider": f"omniroute:{model}"}
    b64 = item.get("b64_json")
    if isinstance(b64, str) and b64.strip():
        return {"url": f"data:image/png;base64,{b64.strip()}", "provider": f"omniroute:{model}"}
    raise OmniRouteError("OmniRoute image response contained neither url nor b64_json.")

async def embed_texts(
    texts: list[str],
    settings: Settings,
    *,
    dimensions: int,
) -> list[list[float]]:
    if not configured(settings):
        raise OmniRouteError("OmniRoute gateway is not configured.")
    model = str(getattr(settings, "omniroute_embedding_model", "") or "").strip()
    if not model:
        raise OmniRouteError("OMNIROUTE_EMBEDDING_MODEL is not configured.")
    if not texts:
        return []

    headers = _headers_for_request(
        settings,
        mode="balanced",
        request_id=str(uuid.uuid4()),
        cache_bypass=False,
    )
    url = _api_base(settings) + "/embeddings"
    results: list[list[float]] = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        for start in range(0, len(texts), 32):
            batch = texts[start:start + 32]
            response = await client.post(
                url,
                headers=headers,
                json={"model": model, "input": batch, "dimensions": dimensions},
            )
            if response.is_error:
                raise OmniRouteError(
                    f"OmniRoute embeddings HTTP {response.status_code}: {_safe_error_text(response)}",
                    status_code=response.status_code,
                    retry_after=response.headers.get("retry-after"),
                )
            payload = response.json()
            rows = payload.get("data") or []
            rows = sorted(
                [row for row in rows if isinstance(row, dict)],
                key=lambda row: int(row.get("index") or 0),
            )
            if len(rows) != len(batch):
                raise OmniRouteError("OmniRoute embeddings returned an incomplete batch.")
            for row in rows:
                vector = row.get("embedding") or []
                values = [float(value) for value in vector]
                if len(values) != dimensions:
                    raise OmniRouteError(
                        f"OmniRoute embedding dimension mismatch: expected {dimensions}, got {len(values)}."
                    )
                results.append(values)
    return results

async def search_web(
    query: str,
    settings: Settings,
    *,
    max_results: int = 10,
    require_current: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    if not configured(settings):
        raise OmniRouteError("OmniRoute gateway is not configured.")

    headers = _headers_for_request(
        settings,
        mode="reliable" if require_current else "balanced",
        request_id=str(uuid.uuid4()),
        cache_bypass=require_current,
    )
    body = {
        "query": query,
        "max_results": max(1, min(int(max_results), 30)),
        "search_type": "news" if require_current else "web",
    }
    url = _api_base(settings) + "/search"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(url, headers=headers, json=body)
    if response.is_error:
        raise OmniRouteError(
            f"OmniRoute search HTTP {response.status_code}: {_safe_error_text(response)}",
            status_code=response.status_code,
            retry_after=response.headers.get("retry-after"),
        )

    payload = response.json()
    raw_results = payload.get("results") or []
    provider = str(payload.get("provider") or "search")
    results: list[dict[str, Any]] = []

    for item in raw_results[: max(1, min(int(max_results), 30))]:
        if not isinstance(item, dict):
            continue
        url_value = str(item.get("url") or "").strip()
        if not url_value.startswith(("http://", "https://")):
            continue
        content = item.get("content")
        full_text = ""
        if isinstance(content, dict):
            full_text = str(content.get("text") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        title = str(item.get("title") or "").strip() or url_value
        published = item.get("published_at")
        host = urlparse(url_value).hostname or ""
        results.append({
            "title": title,
            "url": url_value,
            "content": (full_text or snippet)[:5000],
            "snippet": snippet[:1800],
            "published_date": str(published) if published else None,
            "domain": host.replace("www.", "", 1),
            "source_type": "web",
            "provider": f"omniroute:{provider}",
        })

    return results, f"omniroute-search:{provider}"


async def probe(settings: Settings) -> dict[str, Any]:
    if not configured(settings):
        return {"configured": False, "reachable": False, "reason": "OMNIROUTE_ENABLED/base URL not configured."}

    origin = _origin(settings)
    headers = _auth_headers(settings)
    result: dict[str, Any] = {
        "configured": True,
        "reachable": False,
        "base_url": _api_base(settings),
        "chat_model_strategy": "auto/*",
        "image_configured": bool(str(getattr(settings, "omniroute_image_model", "") or "").strip()),
        "embeddings_configured": bool(str(getattr(settings, "omniroute_embedding_model", "") or "").strip()),
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            ping = await client.get(origin + "/api/health/ping", headers=headers)
            result["reachable"] = not ping.is_error
            result["health_status"] = ping.status_code
            if not ping.is_error:
                try:
                    result["health"] = ping.json()
                except Exception:
                    result["health"] = {"text": ping.text[:300]}

                try:
                    models = await client.get(_api_base(settings) + "/models", headers=headers)
                    if not models.is_error:
                        payload = models.json()
                        rows = payload.get("data") if isinstance(payload, dict) else []
                        if isinstance(rows, list):
                            result["model_count"] = len(rows)
                            result["auto_models"] = [
                                str(row.get("id"))
                                for row in rows
                                if isinstance(row, dict) and str(row.get("id") or "").startswith("auto")
                            ][:30]
                except Exception:
                    pass

                try:
                    card = await client.get(origin + "/.well-known/agent.json", headers=headers)
                    if not card.is_error:
                        payload = card.json()
                        if isinstance(payload, dict):
                            result["a2a_agent_card"] = {
                                "name": payload.get("name"),
                                "version": payload.get("version"),
                            }
                except Exception:
                    pass
            else:
                result["error"] = _safe_error_text(ping)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
    return result
