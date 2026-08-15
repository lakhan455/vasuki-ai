\
from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any


_IMAGES = {
    "python": "python:3.12-slim",
    "javascript": "node:22-alpine",
    "typescript": "node:22-alpine",
}

_ALLOWED_COMMAND = re.compile(
    r"^(python|python3|pytest|node|npm|npx|pnpm|yarn)\b",
    re.I,
)


def sandbox_status() -> dict[str, Any]:
    docker = shutil.which("docker")

    return {
        "available": bool(docker),
        "engine": "docker" if docker else None,
        "network": "disabled",
        "filesystem": "temporary isolated workspace",
        "memory_mb": 384,
        "cpu_limit": 0.75,
        "pids_limit": 96,
        "docker_path": docker,
    }


def _safe_path(value: str) -> str:
    clean = value.replace("\\", "/").strip("/")

    if (
        not clean
        or clean.startswith(".")
        or ".." in clean.split("/")
    ):
        raise ValueError(f"Unsafe file path: {value}")

    return clean


async def run_sandbox(
    files: dict[str, str],
    *,
    runtime: str,
    command: str,
    timeout_seconds: int = 25,
) -> dict[str, Any]:
    status = sandbox_status()

    if not status["available"]:
        return {
            "ok": False,
            "available": False,
            "error": "Docker is not installed or not available to the backend process.",
            "status": status,
        }

    runtime = runtime.strip().lower()

    if runtime not in _IMAGES:
        raise ValueError("runtime must be python, javascript or typescript")

    command = command.strip()

    if len(command) > 1000 or not _ALLOWED_COMMAND.search(command):
        raise ValueError(
            "Test command must begin with python, pytest, node, npm, npx, pnpm or yarn."
        )

    timeout_seconds = max(1, min(60, int(timeout_seconds)))

    started = time.perf_counter()
    container_name = f"vasuki-v12-{uuid.uuid4().hex[:12]}"

    with tempfile.TemporaryDirectory(prefix="vasuki-v12-") as temp:
        root = Path(temp)

        for name, content in files.items():
            safe = _safe_path(name)
            target = root / safe
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content), encoding="utf-8", newline="\n")

        image = _IMAGES[runtime]

        docker_command = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            "none",
            "--memory",
            "384m",
            "--cpus",
            "0.75",
            "--pids-limit",
            "96",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--read-only",
            "--tmpfs",
            "/workspace:rw,size=96m,uid=65534,gid=65534",
            "--tmpfs",
            "/tmp:rw,size=64m,uid=65534,gid=65534",
            "--user",
            "65534:65534",
            "-v",
            f"{root.resolve()}:/src:ro",
            image,
            "sh",
            "-lc",
            f"cp -R /src/. /workspace/ && cd /workspace && {command}",
        ]

        process = await asyncio.create_subprocess_exec(
            *docker_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        timed_out = False

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            timed_out = True
            process.kill()

            try:
                await process.wait()
            except Exception:
                pass

            cleanup = await asyncio.create_subprocess_exec(
                "docker",
                "rm",
                "-f",
                container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await cleanup.wait()

            stdout = b""
            stderr = b"Sandbox execution timed out."

        return {
            "ok": not timed_out and process.returncode == 0,
            "available": True,
            "runtime": runtime,
            "command": command,
            "exit_code": process.returncode,
            "timed_out": timed_out,
            "duration_ms": round(
                (time.perf_counter() - started) * 1000,
                2,
            ),
            "stdout": stdout.decode("utf-8", errors="replace")[-20000:],
            "stderr": stderr.decode("utf-8", errors="replace")[-20000:],
            "isolation": {
                "network": "none",
                "read_only_root": True,
                "capabilities": "ALL dropped",
                "no_new_privileges": True,
                "memory_mb": 384,
                "cpu_limit": 0.75,
                "pids_limit": 96,
            },
        }
