from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ConnectorStatus:
    id: str
    label: str
    category: str
    state: str
    configured: bool
    read_capable: bool
    write_capable: bool
    permission_required_for_write: bool
    note: str
    capabilities: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["capabilities"] = list(self.capabilities)
        return value


def _configured(value: Any) -> bool:
    return bool(str(value or "").strip())


def connector_snapshot(settings: Any) -> list[dict[str, Any]]:
    github = _configured(getattr(settings, "v11_github_token", ""))
    web = bool(
        _configured(getattr(settings, "tavily_api_key", ""))
        or _configured(getattr(settings, "exa_api", ""))
        or (
            bool(getattr(settings, "omniroute_search_enabled", False))
            and _configured(getattr(settings, "omniroute_base_url", ""))
        )
    )
    documents = bool(
        _configured(getattr(settings, "supabase_url", ""))
        and (
            _configured(getattr(settings, "supabase_secret_key", ""))
            or _configured(getattr(settings, "supabase_service_role_key", ""))
        )
        and _configured(getattr(settings, "google_gemini_api", ""))
    )

    active = [
        ConnectorStatus(
            id="github",
            label="GitHub",
            category="developer",
            state="connected" if github else "needs_configuration",
            configured=github,
            read_capable=True,
            write_capable=True,
            permission_required_for_write=True,
            note=(
                "Repository read/write tools are available. Writes require one-time permission."
                if github
                else "Configure the existing backend GitHub token to enable repository tools."
            ),
            capabilities=(
                "read-file",
                "read-issue",
                "compare",
                "create-branch",
                "write-file",
                "create-pr",
            ),
        ),
        ConnectorStatus(
            id="web",
            label="Live web research",
            category="research",
            state="connected" if web else "needs_configuration",
            configured=web,
            read_capable=True,
            write_capable=False,
            permission_required_for_write=False,
            note=(
                "Current web verification is available."
                if web
                else "Configure Tavily, Exa, or OmniRoute search for current web evidence."
            ),
            capabilities=("search", "current-fact-verification", "deep-research"),
        ),
        ConnectorStatus(
            id="user_files",
            label="Files & project knowledge",
            category="workspace",
            state="connected" if documents else "needs_configuration",
            configured=documents,
            read_capable=True,
            write_capable=True,
            permission_required_for_write=False,
            note=(
                "User-scoped files, documents and project knowledge are available."
                if documents
                else "Backend document storage is not fully configured."
            ),
            capabilities=("upload", "search", "project-context", "document-analysis"),
        ),
    ]

    future = [
        ConnectorStatus(
            id="gmail",
            label="Gmail",
            category="communication",
            state="connection_backend_required",
            configured=False,
            read_capable=False,
            write_capable=False,
            permission_required_for_write=True,
            note="OAuth connector backend is required before Vasuki can read or send Gmail.",
            capabilities=("future-read-mail", "future-draft-mail"),
        ),
        ConnectorStatus(
            id="google_drive",
            label="Google Drive",
            category="workspace",
            state="connection_backend_required",
            configured=False,
            read_capable=False,
            write_capable=False,
            permission_required_for_write=True,
            note="OAuth connector backend is required before Drive files can be accessed.",
            capabilities=("future-search-files", "future-read-files"),
        ),
        ConnectorStatus(
            id="google_calendar",
            label="Google Calendar",
            category="productivity",
            state="connection_backend_required",
            configured=False,
            read_capable=False,
            write_capable=False,
            permission_required_for_write=True,
            note="OAuth connector backend is required before calendar access is enabled.",
            capabilities=("future-read-events", "future-create-events"),
        ),
        ConnectorStatus(
            id="slack",
            label="Slack",
            category="communication",
            state="connection_backend_required",
            configured=False,
            read_capable=False,
            write_capable=False,
            permission_required_for_write=True,
            note="Slack OAuth/app installation is required before workspace access is enabled.",
            capabilities=("future-search-messages", "future-send-message"),
        ),
    ]

    return [item.to_dict() for item in [*active, *future]]


def health_snapshot(settings: Any) -> dict[str, Any]:
    connectors = connector_snapshot(settings)
    configured = sum(1 for item in connectors if item["configured"])
    return {
        "ok": True,
        "version": "v65",
        "name": "Vasuki Connected Apps Foundation",
        "configured_connectors": configured,
        "connectors": connectors,
        "security": {
            "secrets_exposed_to_frontend": False,
            "write_actions_require_permission_when_supported": True,
            "unconfigured_apps_are_never_reported_as_connected": True,
        },
        "new_database_migration_required": False,
        "new_api_key_required_for_existing_features": False,
    }
