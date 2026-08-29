from __future__ import annotations

from typing import Any


def tool_hub_health(settings: Any) -> dict[str, Any]:
    supabase_ready = bool(
        str(getattr(settings, "supabase_url", "") or "").strip()
        and str(
            getattr(settings, "supabase_service_role_key", None)
            or getattr(settings, "supabase_secret_key", None)
            or ""
        ).strip()
    )
    github_ready = bool(str(getattr(settings, "v11_github_token", "") or "").strip())
    video_ready = bool(
        str(getattr(settings, "v11_video_api_base_url", "") or "").strip()
        and str(getattr(settings, "v11_video_api_key", "") or "").strip()
    )
    live_search_ready = bool(
        str(getattr(settings, "tavily_api_key", "") or "").strip()
        or str(getattr(settings, "exa_api", "") or "").strip()
        or (
            bool(getattr(settings, "omniroute_enabled", False))
            and bool(getattr(settings, "omniroute_search_enabled", False))
            and str(getattr(settings, "omniroute_base_url", "") or "").strip()
        )
    )
    return {
        "ok": True,
        "version": "v48",
        "name": "Vasuki Unified Tools Hub",
        "tools": [
            {"id": "web-search", "name": "Web Search", "status": "ready", "native": True},
            {"id": "deep-research", "name": "Deep Research", "status": "ready", "native": True},
            {
                "id": "live-knowledge",
                "name": "Continuous Live Knowledge",
                "status": "ready" if (supabase_ready and live_search_ready) else "needs-search-or-supabase",
                "native": True,
            },
            {"id": "image-generation", "name": "Image Generation", "status": "ready", "native": True},
            {"id": "image-editing", "name": "Image Editing + Vision", "status": "ready", "native": True},
            {"id": "file-analysis", "name": "File Analysis", "status": "ready", "native": True},
            {"id": "data-analysis", "name": "Data Analysis", "status": "ready", "native": True},
            {"id": "voice", "name": "Voice", "status": "ready", "native": True},
            {"id": "memory", "name": "Memory", "status": "ready" if supabase_ready else "needs-supabase", "native": True},
            {"id": "projects", "name": "Projects", "status": "ready", "native": True},
            {"id": "scheduled-tasks", "name": "Scheduled Tasks", "status": "ready" if supabase_ready else "needs-supabase", "native": True},
            {"id": "file-library", "name": "File Library", "status": "ready" if supabase_ready else "needs-supabase", "native": True},
            {"id": "coding-agent", "name": "Coding Agent", "status": "ready", "native": True},
            {"id": "github", "name": "GitHub", "status": "ready" if github_ready else "needs-token", "native": True},
            {"id": "video", "name": "Video Generation", "status": "ready" if video_ready else "optional-provider", "native": True},
            {"id": "mcp-apps", "name": "MCP / Connected Apps", "status": "optional-config", "native": False},
            {"id": "computer-use", "name": "Computer Use", "status": "not-enabled", "native": False},
        ],
        "notes": {
            "computer_use": "ChatGPT's hosted computer-use environment is proprietary. Vasuki keeps this disabled until a sandbox/remote browser provider is explicitly configured.",
            "connected_apps": "Google Drive/Gmail/Calendar/Slack require OAuth credentials or MCP servers; V48 exposes the tool hub without inventing credentials.",
            "data_analysis": "V48 adds safe deterministic CSV/TSV/JSON/XLSX profiling without arbitrary server code execution.",
        },
        "new_api_key_required": False,
        "new_database_migration_required": False,
        "new_python_dependency": "openpyxl",
    }
