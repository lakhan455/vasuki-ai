from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any

from app.v31.coding_spec import CodingSpec


@dataclass(frozen=True, slots=True)
class ImpactPlan:
    version: str
    primary_files: tuple[str, ...]
    related_files: tuple[str, ...]
    test_files: tuple[str, ...]
    config_files: tuple[str, ...]
    dependency_order: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("primary_files", "related_files", "test_files", "config_files", "dependency_order"):
            data[key] = list(data[key])
        return data


_CONFIG_NAMES = {
    "package.json", "pyproject.toml", "requirements.txt", "render.yaml",
    "vercel.json", "next.config.ts", "next.config.js", "vite.config.ts",
    "vite.config.js", "build.gradle", "build.gradle.kts", "dockerfile",
}


def build_impact_plan(
    spec: CodingSpec,
    existing_files: list[dict[str, str]] | None = None,
) -> ImpactPlan:
    rows = existing_files or []
    paths = [str(item.get("path") or "").replace("\\", "/") for item in rows]
    primary: list[str] = []

    for target in spec.target_paths:
        target_low = target.casefold()
        target_name = PurePosixPath(target_low).name
        for path in paths:
            low = path.casefold()
            if low == target_low or PurePosixPath(low).name == target_name:
                if path not in primary:
                    primary.append(path)

    if not primary:
        objective = spec.objective.casefold()
        for path in paths:
            stem = PurePosixPath(path).stem.casefold()
            if stem and len(stem) >= 3 and re.search(rf"\b{re.escape(stem)}\b", objective):
                primary.append(path)
                if len(primary) >= 5:
                    break

    terms = {
        PurePosixPath(path).stem.casefold()
        for path in primary
        if PurePosixPath(path).stem
    }
    related: list[str] = []
    for item in rows:
        path = str(item.get("path") or "").replace("\\", "/")
        if not path or path in primary:
            continue
        content = str(item.get("content") or "")[:14000].casefold()
        if any(term and term in content for term in terms):
            related.append(path)
        if len(related) >= 8:
            break

    tests = [
        path for path in paths
        if any(part in path.casefold() for part in ("/test", "/tests/", ".test.", ".spec.", "test_"))
    ][:8]
    configs = [
        path for path in paths
        if PurePosixPath(path.casefold()).name in _CONFIG_NAMES
    ][:8]

    order: list[str] = []
    for group in (primary, related, tests, configs):
        for path in group:
            if path not in order:
                order.append(path)

    return ImpactPlan(
        version="v32",
        primary_files=tuple(primary[:6]),
        related_files=tuple(related[:8]),
        test_files=tuple(tests),
        config_files=tuple(configs),
        dependency_order=tuple(order[:16]),
    )


def impact_engine_health() -> dict[str, Any]:
    return {
        "version": "v32",
        "name": "Code Impact Engine",
        "features": [
            "target-file-resolution",
            "content-reference-impact-scan",
            "test-file-awareness",
            "config-file-awareness",
            "bounded-dependency-order",
        ],
        "whole_repository_prompt_dump": False,
        "extra_provider_call_required": False,
    }
