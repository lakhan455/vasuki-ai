from __future__ import annotations

# VASUKI_V16_TESTS

import asyncio
import json

from app.v16.autonomous_coder import (
    build_autonomous_project,
    _generate_batch,
    coder_health,
    normalize_manifest,
    parse_file_markers,
    validate_files,
)


class Settings:
    v16_max_project_files = 12
    v16_generation_batch_size = 2
    v16_generation_concurrency = 2
    v16_repair_attempts = 1
    v16_docker_sandbox_enabled = False
    v11_github_token = None
    v16_netlify_token = None
    v16_vercel_deploy_hook_url = ""


def test_manifest_is_compact_and_safe():
    manifest = normalize_manifest(
        {
            "project_name": "Demo App",
            "files": [
                {
                    "path": "../bad.py",
                    "purpose": "bad",
                },
                {
                    "path": "src/app.py",
                    "purpose": "entry",
                    "order": 1,
                },
            ],
            "powershell": [
                "python src/app.py",
                "shutdown /s",
            ],
        },
        max_files=8,
    )
    assert manifest["project_name"] == "Demo-App"
    assert [item["path"] for item in manifest["files"]][:1] == [
        "src/app.py"
    ]
    assert "shutdown /s" not in manifest["powershell"]


def test_file_markers_ignore_truncated_tail():
    raw = (
        "<<<FILE:a.py>>>\nprint('a')\n<<<END_FILE>>>\n"
        "<<<FILE:b.py>>>\nprint('truncated')"
    )
    parsed = parse_file_markers(raw)
    assert parsed == {"a.py": "print('a')"}


def test_validation_detects_python_syntax_error():
    result = validate_files({"app.py": "def broken(:\n    pass"})
    assert result["ok"] is False
    assert "app.py" in result["failed"]


def test_agent_builds_files_without_large_json():
    calls = []

    async def fake_chat(messages):
        calls.append(messages)
        user = messages[-1]["content"]
        if "Plan at most" in user:
            return (
                json.dumps(
                    {
                        "project_name": "demo",
                        "summary": "demo",
                        "language": "Python",
                        "framework": "standard-library",
                        "files": [
                            {
                                "path": "app.py",
                                "purpose": "entrypoint",
                                "depends_on": [],
                                "order": 1,
                            },
                            {
                                "path": "README.md",
                                "purpose": "docs",
                                "depends_on": [],
                                "order": 2,
                            },
                        ],
                        "powershell": ["python app.py"],
                        "run_commands": ["python app.py"],
                        "notes": [],
                    }
                ),
                "fake-manifest",
            )
        if "app.py" in user and "README.md" in user:
            return (
                "<<<FILE:app.py>>>\nprint('ok')\n<<<END_FILE>>>\n"
                "<<<FILE:README.md>>>\n# Demo\n<<<END_FILE>>>",
                "fake-builder",
            )
        raise AssertionError("unexpected fake prompt")

    project, telemetry = asyncio.run(
        build_autonomous_project(
            "create a tiny app",
            chat=fake_chat,
            settings=Settings(),
        )
    )
    contents = {
        item["path"]: item["content"]
        for item in project["files"]
    }
    assert contents["app.py"] == "print('ok')"
    assert telemetry["validation"]["ok"] is True
    assert telemetry["batch_count"] == 1


def test_health_reports_v16_without_migration():
    health = coder_health(Settings())
    assert health["version"] == "v16"
    assert health["db_migration_required"] is False
    assert health["new_api_key_required_for_core"] is False
    assert "unterminated-json-project-failure" in health["fixes"]

def test_batch_failure_recovers_files_individually():
    async def scenario():
        calls = 0

        async def fake_chat(messages):
            nonlocal calls
            calls += 1
            user = messages[-1]["content"]

            if calls == 1:
                raise RuntimeError(
                    "temporary batch provider failure"
                )

            path = (
                "src/a.py"
                if "PATH: src/a.py" in user
                else "src/b.py"
            )
            return (
                f"<<<FILE:{path}>>>\n"
                f"print({path!r})\n"
                "<<<END_FILE>>>",
                "fake-provider",
            )

        manifest = {
            "project_name": "demo",
            "summary": "demo",
            "language": "python",
            "framework": "python",
            "files": [
                {
                    "path": "src/a.py",
                    "purpose": "a",
                    "depends_on": [],
                    "order": 1,
                },
                {
                    "path": "src/b.py",
                    "purpose": "b",
                    "depends_on": [],
                    "order": 2,
                },
            ],
            "powershell": [],
            "run_commands": [],
            "notes": [],
        }

        files, providers, initially_missing = (
            await _generate_batch(
                fake_chat,
                "build demo",
                manifest,
                manifest["files"],
                {},
            )
        )

        assert set(files) == {"src/a.py", "src/b.py"}
        assert providers
        assert set(initially_missing) == {
            "src/a.py",
            "src/b.py",
        }

    asyncio.run(scenario())
