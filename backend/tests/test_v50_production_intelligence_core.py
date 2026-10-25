from types import SimpleNamespace

from app.config import Settings
from app.services import research
from app.v50.provider_guard import model_candidates, should_try_model_fallback
from app.v50.telemetry import record_degraded, snapshot
from app.v50.truth import (
    assess_current_evidence,
    extract_sources_from_context,
    should_fail_closed,
)


def _src(url, source_type, content="Current official information", date="2026-10-24"):
    return {
        "url": url,
        "source_type": source_type,
        "content": content,
        "published_date": date,
        "title": "Source",
    }


def test_v50_config_and_fixed_v49_setting():
    settings = Settings(_env_file=None)
    assert settings.v49_1_llm_fallback_enabled is True
    assert settings.v50_generic_truth_guard_enabled is True
    assert settings.v50_model_fallback_enabled is True
    assert settings.groq_fast_model == "openai/gpt-oss-20b"


def test_research_hindi_encoding_is_real_unicode():
    all_terms = " ".join(
        research.FRESHNESS_TERMS
        + research.OFFICEHOLDER_TERMS
        + research.INDIA_TERMS
    )
    assert "अभी" in all_terms
    assert "मुख्यमंत्री" in all_terms
    assert "भारत" in all_terms
    assert "à¤" not in all_terms
    assert "à¥" not in all_terms


def test_high_stakes_current_fact_accepts_official_source():
    assessment = assess_current_evidence(
        "Who is the current CEO of Example?",
        [_src("https://example.gov.in/leader", "official")],
        require_current=True,
    )
    assert assessment.safe_to_answer is True
    assert should_fail_closed(assessment) is False
    assert assessment.safe_to_store is False


def test_high_stakes_current_fact_fails_closed_on_weak_single_source():
    assessment = assess_current_evidence(
        "Who is the current founder of Example?",
        [_src("https://random-blog.example/post", "other")],
        require_current=True,
    )
    assert assessment.safe_to_answer is False
    assert should_fail_closed(assessment) is True


def test_two_independent_trusted_sources_are_store_safe():
    assessment = assess_current_evidence(
        "latest RBI policy update",
        [
            _src("https://reuters.com/a", "reputable_news"),
            _src("https://business-standard.com/b", "trusted_reference"),
        ],
        require_current=True,
    )
    assert assessment.safe_to_answer is True
    assert assessment.safe_to_store is True
    assert assessment.independent_domains == 2


def test_context_source_extraction():
    context = """[1] ENTITY: Example
SOURCE TYPE: official
TITLE: Official profile
URL: https://example.gov.in/profile
PUBLISHED/UPDATED: 2026-10-24
CONTENT:
Example Person is the current CEO.

[2] ENTITY: Example
TYPE: reputable_news
TITLE: Report
URL: https://reuters.com/example
DATE: 2026-10-24
CONTENT:
Example Person continues as CEO."""
    rows = extract_sources_from_context(context)
    assert len(rows) == 2
    assert rows[0]["source_type"] == "official"
    assert rows[1]["url"] == "https://reuters.com/example"


def test_provider_model_fallback_candidates():
    settings = SimpleNamespace(
        v50_model_fallback_enabled=True,
        v50_openrouter_fallback_models="z-ai/glm-5.2:free, another/model",
    )
    assert model_candidates(
        "openrouter",
        settings,
        primary="openai/gpt-4.1-mini",
    ) == [
        "openai/gpt-4.1-mini",
        "z-ai/glm-5.2:free",
        "another/model",
    ]


def test_model_fallback_status_policy():
    assert should_try_model_fallback(status_code=404, error_text="model not found")
    assert should_try_model_fallback(status_code=402, error_text="payment required")
    assert should_try_model_fallback(status_code=429, error_text="rate limited")
    assert not should_try_model_fallback(status_code=401, error_text="unauthorized")


def test_degraded_telemetry_redacts_secrets():
    record_degraded("web", "search", "api_key=super-secret-value timeout")
    data = snapshot(limit=10)
    text = str(data)
    assert "super-secret-value" not in text
    assert "[redacted]" in text
