from __future__ import annotations

# VASUKI_V15_TESTS

import io
import json
import zipfile

from app.v15.coding_agent import (
    build_project_prompt,
    coder_health,
    extract_zip_text_files,
    merge_existing_files,
    normalize_project_payload,
    package_project_response,
    parse_project_response,
)


def sample_payload():
    return {
        "project_name": "demo-app",
        "summary": "Demo",
        "language": "TypeScript",
        "framework": "Next.js",
        "files": [
            {
                "path": "index.html",
                "content": "<html><head></head><body>Hello</body></html>",
            },
            {"path": "style.css", "content": "body{font-family:sans-serif}"},
        ],
        "powershell": ["npm install", "npm run dev"],
        "run_commands": ["npm run dev"],
        "notes": ["No secrets included."],
    }


def test_parse_fenced_json():
    raw = "```json\\n" + json.dumps(sample_payload()) + "\\n```"
    project = parse_project_response(raw)
    assert project["project_name"] == "demo-app"
    assert any(
        file["path"] == "README.md" for file in project["files"]
    )


def test_rejects_path_traversal_but_keeps_safe_files():
    payload = sample_payload()
    payload["files"].insert(
        0, {"path": "../evil.py", "content": "bad"}
    )
    project = normalize_project_payload(payload)
    assert all(".." not in file["path"] for file in project["files"])


def test_package_returns_zip_artifact():
    response = package_project_response(
        sample_payload(), provider="test"
    )
    assert response["ok"] is True
    assert response["files"][0]["mime_type"] == "application/zip"
    assert response["files"][0]["name"].endswith(".zip")
    assert "Expand-Archive" in response["powershell"][0]


def test_extract_zip_text_files():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("src/app.py", "print('ok')")
        zf.writestr("node_modules/x.js", "skip")
    files = extract_zip_text_files(buf.getvalue())
    assert files == [
        {"path": "src/app.py", "content": "print('ok')"}
    ]


def test_merge_existing_files_preserves_unchanged():
    existing = [
        {"path": "a.txt", "content": "A"},
        {"path": "b.txt", "content": "OLD"},
    ]
    generated = normalize_project_payload({
        "project_name": "x",
        "files": [{"path": "b.txt", "content": "NEW"}],
    })
    merged = merge_existing_files(existing, generated)
    contents = {
        item["path"]: item["content"] for item in merged["files"]
    }
    assert contents["a.txt"] == "A"
    assert contents["b.txt"] == "NEW"


def test_prompt_contains_existing_project_context():
    prompt = build_project_prompt(
        "Fix login",
        planner_context={"steps": ["inspect", "fix"]},
        existing_files=[
            {"path": "app.py", "content": "print('x')"}
        ],
    )
    assert "Fix login" in prompt
    assert "app.py" in prompt
    assert "inspect" in prompt


def test_health_has_no_migration_or_key():
    health = coder_health()
    assert health["version"] == "v15"
    assert health["db_migration_required"] is False
    assert health["new_api_key_required"] is False
