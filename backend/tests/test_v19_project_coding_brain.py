from pathlib import Path

from app.v19.project_coding_brain import (
    build_project_coding_context,
    decide_project_coding,
    project_coding_health,
    rank_project_files,
)


def test_active_project_fix_needs_files():
    d = decide_project_coding(
        [{"role": "user", "content": "fix this login bug"}],
        project_id="vasuki-ai",
    )
    assert d.action == "debug-repair"
    assert d.needs_project_files is True
    assert d.needs_dependency_impact_check is True
    assert d.needs_test_plan is True


def test_followup_inherits_coding_request():
    d = decide_project_coding(
        [
            {"role": "user", "content": "FastAPI /api/login returns AttributeError after deploy"},
            {"role": "assistant", "content": "I can inspect it."},
            {"role": "user", "content": "isko fix karo"},
        ],
        project_id="vasuki-ai",
    )
    assert d.is_followup is True
    assert d.action == "debug-repair"
    assert "FastAPI /api/login" in d.reference_text


def test_file_symbol_error_extraction():
    d = decide_project_coding(
        [{
            "role": "user",
            "content": "Fix `backend/app/main_v5.py` function `chat_stream_v5` AttributeError.",
        }],
        project_id="vasuki-ai",
    )
    assert "backend/app/main_v5.py" in d.explicit_files
    assert "chat_stream_v5" in d.symbol_hints
    assert "AttributeError" in d.error_signatures


def test_non_coding_project_question_skips_files():
    d = decide_project_coding(
        [{"role": "user", "content": "What is my project goal?"}],
        project_id="vasuki-ai",
    )
    assert d.needs_project_files is False


def test_ranker_prefers_explicit_file():
    rows = [
        {"path": "backend/app/main_v5.py", "metadata": {"signals": {"symbols": ["chat_stream_v5"], "imports": ["app.main"], "routes": ["/api/chat/stream"]}}},
        {"path": "backend/app/other.py", "metadata": {"signals": {"symbols": ["unrelated"], "imports": [], "routes": []}}},
    ]
    d = decide_project_coding(
        [{"role": "user", "content": "Fix backend/app/main_v5.py function chat_stream_v5"}],
        project_id="vasuki-ai",
    )
    ranked = rank_project_files(
        "Fix backend/app/main_v5.py function chat_stream_v5",
        rows,
        decision=d,
        limit=2,
    )
    assert ranked[0] == "backend/app/main_v5.py"


def test_deploy_prefers_render_config():
    rows = [
        {"path": "render.yaml", "metadata": {"signals": {}}},
        {"path": "backend/app/service.py", "metadata": {"signals": {}}},
    ]
    d = decide_project_coding(
        [{"role": "user", "content": "deployment build failed on Render config"}],
        project_id="vasuki-ai",
    )
    ranked = rank_project_files(
        "deployment build failed on Render config",
        rows,
        decision=d,
        limit=2,
    )
    assert ranked[0] == "render.yaml"


def test_context_has_impact_and_test_guards():
    d = decide_project_coding(
        [{"role": "user", "content": "fix auth bug"}],
        project_id="vasuki-ai",
    )
    context = build_project_coding_context(
        d,
        [{
            "path": "backend/auth.py",
            "content_text": "def authorize():\n    return True\n",
            "metadata": {"signals": {"symbols": ["authorize"], "imports": [], "routes": []}},
        }],
    )
    assert "definitions -> imports -> callers -> routes -> tests" in context
    assert "smallest useful regression-test plan" in context
    assert "[PROJECT FILE 1] backend/auth.py" in context


def test_health_safe_additive():
    health = project_coding_health()
    assert health["version"] == "v19.2"
    assert health["uses_existing_project_kb"] is True
    assert health["new_db_migration_required"] is False
    assert health["new_api_key_required"] is False
    assert health["extra_provider_call_required"] is False
    assert health["arbitrary_server_code_execution"] is False


def test_main_v11_phase2_integration_present():
    backend = Path(__file__).resolve().parents[1]
    source = (backend / "app" / "main_v11.py").read_text(encoding="utf-8")
    assert "VASUKI_V19_PHASE2_PROJECT_CODING_BRAIN_INTEGRATION" in source
    assert "v10.legacy._private_context = _v19_phase2_private_context" in source
    assert '@app.get("/health/v19-phase2")' in source


def test_frontend_cleanup_and_smart_files_fix():
    repo = Path(__file__).resolve().parents[2]
    source = (repo / "frontend" / "components" / "ChatApp.tsx").read_text(encoding="utf-8")
    assert '<div className="pv-header-right">' not in source
    assert "pv-living-mind-badge" not in source
    assert "Chat: Unlimited" not in source
    assert "pv-saved-indicator" not in source
    duplicate = "} else if (shouldUseSmartFiles) {\n\n      } else if (shouldUseSmartFiles) {"
    assert duplicate not in source
    assert "Vasuki Core · V19 Context Brain · online" in source
