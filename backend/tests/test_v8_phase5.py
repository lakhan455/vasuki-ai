from app.schemas import ChatRequest
from app.services.chat_v7 import _provider_family
from app.services.project_memory_auto_v8 import extract_project_memory_candidates


def test_phase5_chat_request_fields_exist():
    fields = ChatRequest.model_fields
    assert "cache_bypass" in fields
    assert "exclude_provider" in fields
    assert "research_mode" in fields


def test_provider_family_groups_groq_variants():
    assert _provider_family("groq") == "groq"
    assert _provider_family("groq_fast") == "groq"
    assert _provider_family("cache:groq") == "groq"
    assert _provider_family("gemini") == "gemini"


def test_project_memory_auto_extract_high_precision():
    rows = [
        {"role": "user", "content": "Is project ka preferred theme deep blue hona chahiye."},
        {"role": "assistant", "content": "Okay."},
        {"role": "user", "content": "Backend FastAPI aur database Supabase use karna hai."},
    ]
    out = extract_project_memory_candidates(rows)
    assert len(out) >= 2
    assert any("Supabase" in item for item in out)


def test_project_memory_auto_extract_ignores_questions():
    rows = [
        {"role": "user", "content": "Kya is project me Supabase use karna chahiye?"},
        {"role": "user", "content": "How should the backend work?"},
    ]
    assert extract_project_memory_candidates(rows) == []


def test_phase5_route_is_registered():
    import app.main_v8_phase5 as phase5

    paths = {getattr(route, "path", "") for route in phase5.app.routes}
    assert "/health/v8-phase5" in paths
    assert "/api/projects/{project_id}/memories/auto-extract" in paths
