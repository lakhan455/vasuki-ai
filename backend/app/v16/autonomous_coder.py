from __future__ import annotations

# VASUKI_V16_AUTONOMOUS_BUILDER

import asyncio
import base64
import io
import json
import os
import posixpath
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Awaitable, Callable

import httpx

from app.v11.coding import syntax_check
from app.v11.github_agent import (
    create_branch as github_create_branch,
    create_pr as github_create_pr,
    put_file as github_put_file,
    read_repo_file as github_read_repo_file,
)
from app.v15.coding_agent import (
    extract_zip_text_files,
    merge_existing_files,
    normalize_project_payload,
    package_project_response,
)

ChatFn = Callable[
    [list[dict[str, Any]]],
    Awaitable[tuple[str, str]],
]

MAX_MANIFEST_CHARS = 18_000
MAX_EXISTING_EXCERPT = 7_000
MAX_FILE_OUTPUT_CHARS = 100_000

BLOCKED_COMMAND_PATTERNS = (
    r"(?i)\bformat\s+[a-z]:",
    r"(?i)\bshutdown\b",
    r"(?i)\brestart-computer\b",
    r"(?i)\bremove-item\s+['\"]?[a-z]:\\",
    r"(?i)\brm\s+-rf\s+/(?:\s|$)",
    r"(?i)\breg\s+delete\b",
    r"(?i)\binvoke-expression\b",
    r"(?i)\biex\b",
)

MANIFEST_SYSTEM = """
You are Vasuki V16 Architect Agent.

Design a COMPLETE but compact software project from the user's request.
Do NOT generate source code yet. Return one small JSON manifest only.

Required schema:
{
  "project_name": "safe-name",
  "summary": "short summary",
  "language": "primary language",
  "framework": "framework/runtime",
  "files": [
    {
      "path": "relative/path.ext",
      "purpose": "what this file does",
      "depends_on": ["relative/other.ext"],
      "order": 1
    }
  ],
  "powershell": ["safe Windows PowerShell install/run/test commands"],
  "run_commands": ["optional cross-platform commands"],
  "notes": ["important implementation notes"]
}

Rules:
- Keep the manifest small.
- Prefer 8-18 files for a normal complete app.
- Use more files only when genuinely required.
- Never include node_modules, build outputs, caches, binaries or secrets.
- Include every bootstrap/config file needed for a runnable MVP.
- Include README.md in the file plan.
- Do not put source code inside the manifest.
- No markdown fences.
""".strip()

FILE_BATCH_SYSTEM = """
You are Vasuki V16 Builder Agent.

Generate COMPLETE source files for the requested project.
Never use TODOs, placeholders, ellipses, "rest of code", or fake imports.

Output each requested file using exactly:
<<<FILE:relative/path.ext>>>
complete file content
<<<END_FILE>>>

Do not output JSON. Do not output commentary outside file markers.
Preserve exact requested paths. Keep each file compact and production-ready.
Never include real secrets; use environment-variable placeholders.
""".strip()

REPAIR_SYSTEM = """
You are Vasuki V16 Repair Agent.
Fix the supplied file so it passes the reported validation problem while
preserving its intended behavior and project interfaces.

Return exactly:
<<<FILE:relative/path.ext>>>
complete corrected file
<<<END_FILE>>>

No commentary, no TODOs, no omitted code.
""".strip()


def _safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip())
    value = re.sub(r"-{2,}", "-", value).strip("-.")
    return (value or "vasuki-project")[:80]


def _safe_path(value: str) -> str:
    raw = (value or "").replace("\\", "/").strip().lstrip("/")
    raw = posixpath.normpath(raw)
    if not raw or raw in {".", ".."} or raw.startswith("../"):
        raise ValueError("Unsafe project path.")
    path = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Unsafe project path.")
    forbidden = {
        ".git", ".next", ".turbo", ".venv", "venv", "node_modules",
        "dist", "build", "coverage", "__pycache__",
    }
    if any(part.casefold() in forbidden for part in path.parts):
        raise ValueError("Dependency/build cache paths are not allowed.")
    return str(path)


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Manifest response did not contain a complete JSON object.")
    candidate = cleaned[start:end + 1]
    value = json.loads(candidate)
    if not isinstance(value, dict):
        raise ValueError("Manifest must be a JSON object.")
    return value


def _safe_commands(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        command = value.strip()
        if not command or len(command) > 500:
            continue
        if any(re.search(pattern, command) for pattern in BLOCKED_COMMAND_PATTERNS):
            continue
        result.append(command)
        if len(result) >= 16:
            break
    return result


def normalize_manifest(
    payload: dict[str, Any],
    *,
    max_files: int,
) -> dict[str, Any]:
    raw_files = payload.get("files")
    if not isinstance(raw_files, list):
        raise ValueError("Manifest did not contain a files list.")

    files: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_files, 1):
        if not isinstance(item, dict):
            continue
        try:
            path = _safe_path(str(item.get("path") or ""))
        except ValueError:
            continue
        key = path.casefold()
        if key in seen:
            continue
        seen.add(key)
        depends_on: list[str] = []
        for dependency in item.get("depends_on") or []:
            if not isinstance(dependency, str):
                continue
            try:
                depends_on.append(_safe_path(dependency))
            except ValueError:
                continue
        try:
            order = int(item.get("order") or index)
        except (TypeError, ValueError):
            order = index
        files.append({
            "path": path,
            "purpose": str(item.get("purpose") or "").strip()[:1200],
            "depends_on": depends_on[:12],
            "order": max(0, min(order, 999)),
        })
        if len(files) >= max_files:
            break

    if not files:
        raise ValueError("Manifest contained no safe source files.")

    if not any(item["path"].casefold() == "readme.md" for item in files):
        files.append({
            "path": "README.md",
            "purpose": "Project setup, run, test and architecture instructions.",
            "depends_on": [],
            "order": 999,
        })

    files.sort(key=lambda item: (item["order"], item["path"].casefold()))
    return {
        "project_name": _safe_name(
            str(payload.get("project_name") or "vasuki-project")
        ),
        "summary": str(payload.get("summary") or "").strip()[:3000],
        "language": str(payload.get("language") or "mixed").strip()[:100],
        "framework": str(payload.get("framework") or "custom").strip()[:160],
        "files": files[:max_files],
        "powershell": _safe_commands(payload.get("powershell")),
        "run_commands": _safe_commands(payload.get("run_commands")),
        "notes": [
            str(value).strip()[:1000]
            for value in (payload.get("notes") or [])
            if isinstance(value, str) and value.strip()
        ][:20],
    }


def parse_file_markers(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    pattern = re.compile(
        r"<<<FILE:([^\n>]+)>>>\s*\n([\s\S]*?)\n<<<END_FILE>>>",
        re.MULTILINE,
    )
    for match in pattern.finditer(text or ""):
        try:
            path = _safe_path(match.group(1).strip())
        except ValueError:
            continue
        content = match.group(2)
        if content.strip():
            result[path] = content[:MAX_FILE_OUTPUT_CHARS].rstrip()
    return result


def _single_file_fallback(text: str, path: str) -> str:
    parsed = parse_file_markers(text)
    if path in parsed:
        return parsed[path]
    cleaned = (text or "").strip()
    fenced = re.match(
        r"^```[^\n]*\n([\s\S]*?)\n```$",
        cleaned,
    )
    if fenced:
        cleaned = fenced.group(1)
    if not cleaned:
        raise ValueError(f"AI returned empty content for {path}.")
    return cleaned[:MAX_FILE_OUTPUT_CHARS].rstrip()


async def _ask(
    chat: ChatFn,
    *,
    system: str,
    user: str,
    attempts: int = 3,
) -> tuple[str, str]:
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            answer, provider = await chat([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
            if answer and answer.strip():
                return answer.strip(), provider or "auto"
            raise RuntimeError("AI returned an empty response.")
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                await asyncio.sleep(0.6 + (attempt * 0.9))
    raise RuntimeError(
        f"AI generation failed after {attempts} attempts: {last_error}"
    )


async def _generate_manifest(
    chat: ChatFn,
    request: str,
    *,
    existing_files: list[dict[str, str]] | None,
    max_files: int,
) -> tuple[dict[str, Any], str, int]:
    existing_inventory = ""
    if existing_files:
        existing_inventory = "\n\nEXISTING PROJECT FILE INVENTORY:\n" + "\n".join(
            f"- {item['path']} ({len(item['content'])} chars)"
            for item in existing_files[:80]
        )
    user_prompt = (
        f"USER REQUEST:\n{request.strip()}\n"
        f"{existing_inventory}\n\n"
        f"Plan at most {max_files} source/config files."
    )

    last_error = ""
    for attempt in range(1, 4):
        raw, provider = await _ask(
            chat,
            system=MANIFEST_SYSTEM,
            user=(
                user_prompt
                if attempt == 1
                else user_prompt
                + "\n\nPrevious manifest was invalid. Return shorter valid JSON only."
            ),
            attempts=2,
        )
        try:
            if len(raw) > MAX_MANIFEST_CHARS:
                raise ValueError("Manifest was too large.")
            return normalize_manifest(
                _extract_json_object(raw),
                max_files=max_files,
            ), provider, attempt
        except Exception as exc:
            last_error = str(exc)

    raise RuntimeError(
        "V16 could not obtain a valid compact project manifest. "
        + last_error
    )


def _manifest_context(manifest: dict[str, Any]) -> str:
    compact = {
        "project_name": manifest["project_name"],
        "summary": manifest["summary"],
        "language": manifest["language"],
        "framework": manifest["framework"],
        "files": [
            {
                "path": item["path"],
                "purpose": item["purpose"],
                "depends_on": item["depends_on"],
            }
            for item in manifest["files"]
        ],
    }
    return json.dumps(compact, ensure_ascii=False)


def _existing_map(
    existing_files: list[dict[str, str]] | None,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in existing_files or []:
        try:
            path = _safe_path(item["path"])
        except Exception:
            continue
        result[path] = item["content"]
    return result


def _batch_prompt(
    request: str,
    manifest: dict[str, Any],
    batch: list[dict[str, Any]],
    existing: dict[str, str],
) -> str:
    sections = [
        "USER REQUEST:",
        request.strip(),
        "",
        "PROJECT MANIFEST:",
        _manifest_context(manifest),
        "",
        "GENERATE THESE FILES NOW:",
    ]
    for item in batch:
        sections.append(
            f"\nPATH: {item['path']}\n"
            f"PURPOSE: {item['purpose']}\n"
            f"DEPENDS ON: {', '.join(item['depends_on']) or 'none'}"
        )
        current = existing.get(item["path"])
        if current is not None:
            sections.append(
                "CURRENT FILE CONTENT (modify it completely as needed):\n"
                + current[:MAX_EXISTING_EXCERPT]
            )
    sections.append(
        "\nReturn every requested file using the exact FILE/END_FILE markers."
    )
    return "\n".join(sections)


async def _generate_batch(
    chat: ChatFn,
    request: str,
    manifest: dict[str, Any],
    batch: list[dict[str, Any]],
    existing: dict[str, str],
) -> tuple[dict[str, str], list[str], list[str]]:
    raw, provider = await _ask(
        chat,
        system=FILE_BATCH_SYSTEM,
        user=_batch_prompt(request, manifest, batch, existing),
        attempts=3,
    )
    parsed = parse_file_markers(raw)
    wanted = {item["path"] for item in batch}
    completed = {
        path: content for path, content in parsed.items()
        if path in wanted
    }
    missing = sorted(wanted - set(completed))
    providers = [provider]

    for path in missing:
        item = next(value for value in batch if value["path"] == path)
        individual_prompt = _batch_prompt(
            request, manifest, [item], existing
        )
        one_raw, one_provider = await _ask(
            chat,
            system=FILE_BATCH_SYSTEM,
            user=individual_prompt,
            attempts=3,
        )
        completed[path] = _single_file_fallback(one_raw, path)
        providers.append(one_provider)

    return completed, providers, missing


def validate_files(files: dict[str, str]) -> dict[str, Any]:
    validate_suffixes = {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".css", ".html",
        ".sql", ".java", ".kt", ".kts", ".c", ".cc", ".cpp", ".h", ".hpp",
        ".cs", ".go", ".rs", ".php", ".rb", ".swift", ".dart", ".vue",
    }
    checks: dict[str, Any] = {}
    for path, content in files.items():
        suffix = PurePosixPath(path).suffix.casefold()
        if suffix not in validate_suffixes:
            checks[path] = {
                "ok": True,
                "language": suffix.lstrip(".") or "text",
                "errors": [],
                "skipped": True,
            }
            continue
        checks[path] = syntax_check(path, content)
    failed = {
        path: result
        for path, result in checks.items()
        if not result.get("ok")
    }
    return {
        "ok": not failed,
        "checks": checks,
        "failed": failed,
    }


async def _repair_failed_files(
    chat: ChatFn,
    request: str,
    manifest: dict[str, Any],
    files: dict[str, str],
    *,
    max_attempts: int,
) -> tuple[dict[str, str], list[dict[str, Any]], list[str]]:
    current = dict(files)
    repairs: list[dict[str, Any]] = []
    providers: list[str] = []

    for attempt in range(1, max(0, max_attempts) + 1):
        validation = validate_files(current)
        failed = validation["failed"]
        if not failed:
            break

        for path, result in failed.items():
            content = current[path]
            prompt = (
                f"USER REQUEST:\n{request}\n\n"
                f"PROJECT:\n{_manifest_context(manifest)}\n\n"
                f"FILE TO REPAIR: {path}\n"
                f"VALIDATION ERRORS:\n"
                f"{json.dumps(result, ensure_ascii=False)}\n\n"
                f"CURRENT CONTENT:\n{content[:MAX_FILE_OUTPUT_CHARS]}"
            )
            raw, provider = await _ask(
                chat,
                system=REPAIR_SYSTEM,
                user=prompt,
                attempts=2,
            )
            current[path] = _single_file_fallback(raw, path)
            providers.append(provider)
            repairs.append({
                "attempt": attempt,
                "path": path,
                "provider": provider,
            })

    return current, repairs, providers


def _docker_image_available(image: str) -> bool:
    if not shutil.which("docker"):
        return False
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def docker_sandbox_validate(
    files: dict[str, str],
    *,
    enabled: bool,
) -> dict[str, Any]:
    runtime = shutil.which("docker")
    snapshot: dict[str, Any] = {
        "enabled": bool(enabled),
        "runtime_available": bool(runtime),
        "network": "disabled",
        "memory_mb": 512,
        "cpu_limit": 1,
        "pids_limit": 128,
        "runs": [],
    }
    if not enabled or not runtime:
        return snapshot

    has_python = any(path.endswith(".py") for path in files)
    has_js = any(path.endswith(".js") for path in files)
    candidates: list[tuple[str, list[str]]] = []
    if has_python and _docker_image_available("python:3.13-alpine"):
        candidates.append((
            "python:3.13-alpine",
            ["python", "-m", "compileall", "-q", "/workspace"],
        ))
    if has_js and _docker_image_available("node:22-alpine"):
        candidates.append((
            "node:22-alpine",
            [
                "sh", "-lc",
                "find /workspace -type f -name '*.js' -print0 "
                "| xargs -0 -r -n1 node --check",
            ],
        ))

    if not candidates:
        snapshot["note"] = (
            "Docker is available, but required local validation images "
            "are not preloaded. V16 never pulls images implicitly."
        )
        return snapshot

    with tempfile.TemporaryDirectory(prefix="vasuki-v16-") as temp:
        root = Path(temp)
        for path, content in files.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        for image, command in candidates:
            args = [
                "docker", "run", "--rm",
                "--network", "none",
                "--memory", "512m",
                "--cpus", "1",
                "--pids-limit", "128",
                "--read-only",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
                "-v", f"{root}:/workspace:ro",
                image,
                *command,
            ]
            try:
                result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    timeout=25,
                    check=False,
                )
                snapshot["runs"].append({
                    "image": image,
                    "ok": result.returncode == 0,
                    "returncode": result.returncode,
                    "stdout": result.stdout[-3000:],
                    "stderr": result.stderr[-3000:],
                })
            except Exception as exc:
                snapshot["runs"].append({
                    "image": image,
                    "ok": False,
                    "error": str(exc)[:1000],
                })

    return snapshot


def tool_catalog() -> list[dict[str, str]]:
    return [
        {
            "name": "project.plan",
            "permission": "automatic",
            "purpose": "Create compact project manifest",
        },
        {
            "name": "files.generate_batch",
            "permission": "automatic",
            "purpose": "Generate complete source files in small batches",
        },
        {
            "name": "files.validate",
            "permission": "automatic",
            "purpose": "Run syntax and structural validation",
        },
        {
            "name": "files.repair",
            "permission": "automatic",
            "purpose": "Self-correct failed generated files",
        },
        {
            "name": "sandbox.validate",
            "permission": "automatic-safe",
            "purpose": "Optional restricted Docker syntax validation",
        },
        {
            "name": "artifact.package",
            "permission": "automatic",
            "purpose": "Create ZIP, README and PowerShell runbook",
        },
        {
            "name": "deploy.github",
            "permission": "owner-confirmation",
            "purpose": "Publish ZIP source to a GitHub branch and PR",
        },
        {
            "name": "deploy.netlify",
            "permission": "owner-confirmation",
            "purpose": "Deploy a static ZIP through Netlify API",
        },
        {
            "name": "deploy.vercel_hook",
            "permission": "owner-confirmation",
            "purpose": "Trigger a configured Vercel deploy hook",
        },
    ]


async def _emit_progress(
    progress,
    stage: str,
    value: int,
    message: str,
) -> None:
    if progress is None:
        return
    await progress(stage, value, message)


async def build_autonomous_project(
    request: str,
    *,
    chat: ChatFn,
    settings: Any,
    existing_files: list[dict[str, str]] | None = None,
    progress=None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    max_files = max(
        4,
        min(40, int(getattr(settings, "v16_max_project_files", 24))),
    )
    batch_size = max(
        1,
        min(4, int(getattr(settings, "v16_generation_batch_size", 3))),
    )
    concurrency = max(
        1,
        min(4, int(getattr(settings, "v16_generation_concurrency", 2))),
    )
    repair_attempts = max(
        0,
        min(3, int(getattr(settings, "v16_repair_attempts", 2))),
    )

    await _emit_progress(
        progress,
        "planning",
        6,
        "Designing project architecture",
    )
    manifest, manifest_provider, manifest_attempts = (
        await _generate_manifest(
            chat,
            request,
            existing_files=existing_files,
            max_files=max_files,
        )
    )
    await _emit_progress(
        progress,
        "planning",
        16,
        f"Architecture ready · {len(manifest['files'])} files planned",
    )

    existing = _existing_map(existing_files)
    batches = [
        manifest["files"][index:index + batch_size]
        for index in range(0, len(manifest["files"]), batch_size)
    ]
    semaphore = asyncio.Semaphore(concurrency)

    async def run_batch(batch: list[dict[str, Any]]):
        async with semaphore:
            return await _generate_batch(
                chat, request, manifest, batch, existing
            )

    await _emit_progress(
        progress,
        "building",
        20,
        f"Generating {len(batches)} code batches",
    )

    tasks = [
        asyncio.create_task(run_batch(batch))
        for batch in batches
    ]
    results = []
    for index, task in enumerate(asyncio.as_completed(tasks), 1):
        results.append(await task)
        percentage = 20 + int(45 * index / max(1, len(tasks)))
        await _emit_progress(
            progress,
            "building",
            percentage,
            f"Code batch {index}/{len(tasks)} complete",
        )

    generated: dict[str, str] = {}
    providers: list[str] = [manifest_provider]
    batch_missing: list[str] = []
    for files, used_providers, missing in results:
        generated.update(files)
        providers.extend(used_providers)
        batch_missing.extend(missing)

    await _emit_progress(
        progress,
        "validating",
        70,
        f"Validating {len(generated)} generated files",
    )

    generated, repairs, repair_providers = await _repair_failed_files(
        chat,
        request,
        manifest,
        generated,
        max_attempts=repair_attempts,
    )
    providers.extend(repair_providers)

    await _emit_progress(
        progress,
        "repairing",
        82,
        (
            f"Self-repair complete · {len(repairs)} repair action(s)"
            if repairs
            else "Validation clean · no repair needed"
        ),
    )

    project_payload = {
        "project_name": manifest["project_name"],
        "summary": manifest["summary"],
        "language": manifest["language"],
        "framework": manifest["framework"],
        "files": [
            {"path": path, "content": content}
            for path, content in generated.items()
        ],
        "powershell": manifest["powershell"],
        "run_commands": manifest["run_commands"],
        "notes": manifest["notes"],
    }
    project = normalize_project_payload(project_payload)

    if existing_files:
        project = merge_existing_files(existing_files, project)

    final_map = {
        item["path"]: item["content"] for item in project["files"]
    }
    validation = validate_files(final_map)

    await _emit_progress(
        progress,
        "sandbox",
        90,
        "Running safe validation sandbox when available",
    )
    sandbox = docker_sandbox_validate(
        final_map,
        enabled=bool(
            getattr(settings, "v16_docker_sandbox_enabled", True)
        ),
    )

    await _emit_progress(
        progress,
        "packaging",
        96,
        "Preparing project ZIP and runbook",
    )

    telemetry = {
        "pipeline": [
            "plan",
            "generate-batches",
            "validate",
            "self-repair",
            "sandbox-validate",
            "package",
        ],
        "manifest_attempts": manifest_attempts,
        "generated_files": len(generated),
        "batch_count": len(batches),
        "batch_recovered_missing_files": sorted(set(batch_missing)),
        "repairs": repairs,
        "validation": validation,
        "sandbox": sandbox,
        "providers": list(
            dict.fromkeys(
                provider for provider in providers if provider
            )
        ),
        "tools": tool_catalog(),
    }
    return project, telemetry

def _zip_text_paths(data: bytes) -> list[dict[str, str]]:
    return extract_zip_text_files(data)


async def publish_zip_to_github(
    settings: Any,
    *,
    zip_data: bytes,
    repo: str,
    branch: str,
    base: str = "main",
    open_pr: bool = True,
) -> dict[str, Any]:
    files = _zip_text_paths(zip_data)
    branch_result = await github_create_branch(
        settings,
        repo,
        branch=branch,
        from_ref=base,
    )

    commits: list[dict[str, Any]] = []
    for item in files:
        encoded = base64.b64encode(
            item["content"].encode("utf-8")
        ).decode("ascii")
        existing_sha = None
        try:
            existing = await github_read_repo_file(
                settings,
                repo,
                item["path"],
                ref=branch,
            )
            existing_sha = str(existing.get("sha") or "") or None
        except Exception:
            existing_sha = None
        result = await github_put_file(
            settings,
            repo,
            path=item["path"],
            content_b64=encoded,
            message=f"Vasuki V16: add/update {item['path']}",
            branch=branch,
            sha=existing_sha,
        )
        commits.append({
            "path": item["path"],
            "commit": result.get("commit", {}).get("sha"),
        })

    pr = None
    if open_pr:
        pr = await github_create_pr(
            settings,
            repo,
            title="Deploy Vasuki generated project",
            head=branch,
            base=base,
            body=(
                "Generated and packaged by Vasuki V16 Autonomous Builder. "
                "Review checks before merging."
            ),
        )

    return {
        "ok": True,
        "repo": repo,
        "branch": branch,
        "files": len(files),
        "branch_result": branch_result,
        "commits": commits,
        "pull_request": pr,
    }


async def deploy_netlify_zip(
    settings: Any,
    *,
    zip_data: bytes,
    site_id: str = "",
) -> dict[str, Any]:
    token = str(
        getattr(settings, "v16_netlify_token", "") or ""
    ).strip()
    if not token:
        raise RuntimeError(
            "Netlify deployment is not configured on the backend."
        )

    files = _zip_text_paths(zip_data)
    if not any(
        PurePosixPath(item["path"]).name.casefold() == "index.html"
        for item in files
    ):
        raise RuntimeError(
            "Direct Netlify ZIP deploy requires a static/built site "
            "containing index.html."
        )

    base = "https://api.netlify.com/api/v1"
    url = (
        f"{base}/sites/{site_id}/deploys"
        if site_id.strip()
        else f"{base}/sites"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/zip",
        "User-Agent": "Vasuki-AI-V16",
    }
    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            url,
            headers=headers,
            content=zip_data,
        )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Netlify API {response.status_code}: "
            f"{response.text[:800]}"
        )
    data = response.json()
    return {
        "ok": True,
        "id": data.get("id"),
        "state": data.get("state"),
        "url": (
            data.get("ssl_url")
            or data.get("deploy_ssl_url")
            or data.get("deploy_url")
            or data.get("url")
        ),
        "admin_url": data.get("admin_url"),
        "raw": data,
    }


async def trigger_vercel_deploy_hook(
    settings: Any,
) -> dict[str, Any]:
    hook = str(
        getattr(settings, "v16_vercel_deploy_hook_url", "") or ""
    ).strip()
    if not hook.startswith("https://"):
        raise RuntimeError(
            "Vercel deploy hook is not configured on the backend."
        )
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(hook)
    if response.status_code >= 400:
        raise RuntimeError(
            f"Vercel deploy hook {response.status_code}: "
            f"{response.text[:800]}"
        )
    try:
        data = response.json()
    except Exception:
        data = {"text": response.text[:2000]}
    return {"ok": True, "result": data}


def coder_health(settings: Any) -> dict[str, Any]:
    return {
        "version": "v16",
        "features": [
            "compact-manifest-planner",
            "batched-multi-file-generation",
            "truncation-recovery-with-file-markers",
            "tool-calling-agent-loop",
            "automatic-syntax-validation",
            "self-correction-repair-loop",
            "restricted-docker-sandbox-validation",
            "complete-zip-and-powershell-artifacts",
            "existing-zip-project-modification",
            "github-publish-and-pr-integration",
            "netlify-static-zip-deployment",
            "vercel-deploy-hook-integration",
        ],
        "fixes": [
            "large-project-single-json-truncation",
            "unterminated-json-project-failure",
        ],
        "db_migration_required": False,
        "new_api_key_required_for_core": False,
        "limits": {
            "max_project_files": max(
                4,
                min(
                    40,
                    int(
                        getattr(
                            settings,
                            "v16_max_project_files",
                            24,
                        )
                    ),
                ),
            ),
            "batch_size": max(
                1,
                min(
                    4,
                    int(
                        getattr(
                            settings,
                            "v16_generation_batch_size",
                            3,
                        )
                    ),
                ),
            ),
        },
        "sandbox": {
            "enabled": bool(
                getattr(
                    settings,
                    "v16_docker_sandbox_enabled",
                    True,
                )
            ),
            "docker_runtime_available": bool(
                shutil.which("docker")
            ),
            "network": "disabled",
            "implicit_image_pull": False,
        },
        "deployment": {
            "github_configured": bool(
                str(
                    getattr(
                        settings,
                        "v11_github_token",
                        "",
                    )
                    or ""
                ).strip()
            ),
            "netlify_configured": bool(
                str(
                    getattr(
                        settings,
                        "v16_netlify_token",
                        "",
                    )
                    or ""
                ).strip()
            ),
            "vercel_hook_configured": str(
                getattr(
                    settings,
                    "v16_vercel_deploy_hook_url",
                    "",
                )
                or ""
            ).startswith("https://"),
            "writes_require_owner_confirmation": True,
        },
        "tools": tool_catalog(),
    }
