from __future__ import annotations
import httpx
from app.config import Settings


async def tavily_search(query: str, settings: Settings, max_results: int = 5) -> list[dict]:
    if not settings.tavily_api_key:
        return []
    payload = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": False,
    }
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        response = await client.post("https://api.tavily.com/search", json=payload)
        response.raise_for_status()
        data = response.json()
    return [
        {
            "title": item.get("title", "Source"),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
            "score": item.get("score"),
        }
        for item in data.get("results", [])
    ]


async def exa_search(query: str, settings: Settings, max_results: int = 5) -> list[dict]:
    if not settings.exa_api:
        return []
    headers = {"x-api-key": settings.exa_api, "Content-Type": "application/json"}
    payload = {
        "query": query,
        "numResults": max_results,
        "useAutoprompt": True,
        "contents": {"text": {"maxCharacters": 1500}},
    }
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        response = await client.post("https://api.exa.ai/search", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    return [
        {
            "title": item.get("title", "Source"),
            "url": item.get("url", ""),
            "content": (item.get("text") or "")[:1500],
            "score": item.get("score"),
        }
        for item in data.get("results", [])
    ]


async def search_web(query: str, settings: Settings, max_results: int = 5) -> tuple[list[dict], str]:
    errors: list[str] = []
    for name, fn in (("tavily", tavily_search), ("exa", exa_search)):
        try:
            results = await fn(query, settings, max_results)
            if results:
                return results, name
        except Exception as exc:  # keep fallback chain alive
            errors.append(f"{name}: {exc}")
    return [], "; ".join(errors) if errors else "No research API configured"
