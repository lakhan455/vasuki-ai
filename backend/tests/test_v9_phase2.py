from app.services.coding_agent_v9 import make_unified_diff, validate_agent_plan
from app.services.project_kb_v9 import (
    build_codebase_map_from_rows,
    detect_language,
    extract_code_signals,
    normalize_project_path,
)

def test_project_path_normalization():
    assert normalize_project_path(r"src\app\main.py") == "src/app/main.py"

def test_project_path_rejects_traversal():
    try:
        normalize_project_path("../secret.txt")
        assert False, "expected ValueError"
    except ValueError:
        pass

def test_language_detection():
    assert detect_language("frontend/app/page.tsx") == "typescript"
    assert detect_language("backend/app/main.py") == "python"

def test_code_signals_find_imports_and_routes():
    signals = extract_code_signals(
        "main.py",
        "from fastapi import FastAPI\n@app.get('/health')\ndef health():\n    return {'ok': True}\n",
    )
    assert "fastapi" in signals["imports"]
    assert "/health" in signals["routes"]
    assert "health" in signals["symbols"]

def test_codebase_map_builds_relationship():
    rows = [
        {"path": "app/main.py", "content_text": "from app.services.foo import run\n"},
        {"path": "app/services/foo.py", "content_text": "def run():\n    return 1\n"},
    ]
    result = build_codebase_map_from_rows(rows)
    assert result["file_count"] == 2
    assert result["languages"]["python"] == 2

def test_agent_plan_validation():
    plan = validate_agent_plan({
        "summary": "x",
        "changes": [{"path": "app/a.py", "action": "update", "content": "print('ok')"}],
        "tests": ["pytest -q"],
    })
    assert plan["changes"][0]["path"] == "app/a.py"

def test_unified_diff():
    diff = make_unified_diff("a.py", "x=1\n", "x=2\n", "update")
    assert "--- a/a.py" in diff
    assert "+++ b/a.py" in diff
    assert "-x=1" in diff
    assert "+x=2" in diff

def test_phase2_routes_registered():
    import app.main_v9_phase2 as phase2
    paths = {getattr(route, "path", "") for route in phase2.app.routes}
    assert "/health/v9-phase2" in paths
    assert "/api/projects/{project_id}/code/patch" in paths
    assert "/api/projects/{project_id}/tests/generate" in paths
    assert "/api/projects/{project_id}/debug" in paths
