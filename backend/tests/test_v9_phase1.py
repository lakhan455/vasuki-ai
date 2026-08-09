from app.services.feature_flags_v9 import bucket
from app.services.memory_policy_v9 import classify_memory, subject_key
from app.services.quality_v9 import rank_for_task
from app.services.research_v9 import decompose_query, deduplicate_sources, verify_citations

def test_research_decomposition():
    assert len(decompose_query("Compare Gemini vs Groq for coding and research")) >= 3

def test_source_dedupe():
    assert len(deduplicate_sources([
        {"url":"https://example.com/a","title":"A"},
        {"url":"https://example.com/a/","title":"B"},
    ])) == 1

def test_citation_support():
    r = verify_citations("FastAPI is a Python web framework [S1].", [{"title":"FastAPI","content":"FastAPI is a modern Python web framework."}])
    assert r["claims_checked"] == 1
    assert r["claims_supported"] == 1

def test_memory_subject_supersedes_version():
    assert classify_memory("Backend FastAPI use karega", "config") == "technical_configuration"
    assert subject_key("Project V7 par hai", "project_fact") == subject_key("Project V9 par hai", "project_fact")

def test_flag_bucket_stable():
    assert bucket("u1","research_v2") == bucket("u1","research_v2")

def test_quality_rank_preserves_members():
    names = ["groq","gemini","openrouter"]
    assert sorted(rank_for_task(names,"code")) == sorted(names)

def test_v9_routes():
    import app.main_v9_phase1 as v9
    paths = {getattr(r, "path", "") for r in v9.app.routes}
    assert "/health/v9-phase1" in paths
    assert "/api/research/v2/verify" in paths
