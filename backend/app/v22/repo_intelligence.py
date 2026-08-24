from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any


@dataclass(frozen=True, slots=True)
class RepoSnapshot:
    version: str
    files: int
    languages: tuple[str, ...]
    routes: tuple[str, ...]
    symbols: tuple[str, ...]
    config_files: tuple[str, ...]
    selected_files: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("languages", "routes", "symbols", "config_files", "selected_files"):
            data[key] = list(data[key])
        return data


_CONFIG = {
    "package.json", "requirements.txt", "pyproject.toml", "render.yaml",
    "vercel.json", "dockerfile", "next.config.ts", "next.config.js",
    "vite.config.ts", "vite.config.js", "build.gradle", "build.gradle.kts",
}


def _signals(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata")
    value = metadata.get("signals", {}) if isinstance(metadata, dict) else {}
    return value if isinstance(value, dict) else {}


def expand_related_files(rows: list[dict[str, Any]], seeds: list[str], *, limit: int = 8) -> list[str]:
    limit = max(1, min(int(limit), 12))
    seed_low = {str(item).replace("\\", "/").casefold() for item in seeds}
    selected: list[str] = []
    seed_symbols: set[str] = set()
    seed_imports: set[str] = set()

    for row in rows:
        path = str(row.get("path") or "").replace("\\", "/")
        low = path.casefold()
        name = PurePosixPath(low).name
        if low in seed_low or name in seed_low or any(seed in low for seed in seed_low):
            if path not in selected:
                selected.append(path)
            sig = _signals(row)
            seed_symbols.update(str(x).casefold() for x in (sig.get("symbols") or []))
            seed_imports.update(str(x).casefold() for x in (sig.get("imports") or []))

    scored: list[tuple[float, str]] = []
    for row in rows:
        path = str(row.get("path") or "").replace("\\", "/")
        if not path or path in selected:
            continue
        low = path.casefold()
        sig = _signals(row)
        symbols = {str(x).casefold() for x in (sig.get("symbols") or [])}
        imports = {str(x).casefold() for x in (sig.get("imports") or [])}
        score = float(len(symbols & seed_imports) * 2 + len(imports & seed_symbols))
        for seed in seed_low:
            stem = PurePosixPath(seed).stem
            if stem and stem in low:
                score += 0.75
        if score > 0:
            scored.append((score, path))

    scored.sort(key=lambda item: (-item[0], item[1].casefold()))
    for _, path in scored:
        if path not in selected:
            selected.append(path)
        if len(selected) >= limit:
            break
    return selected[:limit]


def build_repo_snapshot(rows: list[dict[str, Any]], selected_files: list[str] | None = None) -> RepoSnapshot:
    languages: set[str] = set()
    routes: list[str] = []
    symbols: list[str] = []
    configs: list[str] = []

    for row in rows[:500]:
        path = str(row.get("path") or "")
        language = str(row.get("language") or "")
        if language:
            languages.add(language)
        name = PurePosixPath(path.casefold()).name
        if name in _CONFIG:
            configs.append(path)
        sig = _signals(row)
        for route in sig.get("routes") or []:
            value = str(route)
            if value not in routes:
                routes.append(value)
        for symbol in sig.get("symbols") or []:
            value = str(symbol)
            if value not in symbols:
                symbols.append(value)

    return RepoSnapshot(
        version="v22",
        files=len(rows),
        languages=tuple(sorted(languages)[:20]),
        routes=tuple(routes[:40]),
        symbols=tuple(symbols[:80]),
        config_files=tuple(configs[:20]),
        selected_files=tuple((selected_files or [])[:12]),
    )


def repo_intelligence_health() -> dict[str, Any]:
    return {
        "version": "v22",
        "name": "Repository Intelligence",
        "features": [
            "project-kb-graph-signals",
            "symbol-route-import-awareness",
            "related-file-expansion",
            "config-file-awareness",
            "bounded-repository-context",
        ],
        "whole_repo_prompt_dump": False,
        "db_migration_required": False,
    }
