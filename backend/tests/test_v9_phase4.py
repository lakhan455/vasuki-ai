from __future__ import annotations

from app.main_v9_phase4 import app
from app.services.jobs_v9 import validate_job_payload
from app.services.platform_v9_phase4 import (
    evaluate_job_policy,
    stable_bucket,
    summarize_usage_rows,
    weighted_variant,
)


def test_phase4_bucket_is_stable():
    first = stable_bucket("user-1", "feature-a")
    second = stable_bucket("user-1", "feature-a")
    assert first == second
    assert 0 <= first < 100


def test_phase4_weighted_variant_is_stable():
    variants = {"control": 50, "fast": 50}
    value = weighted_variant("user-1", "refresh", variants)
    assert value in variants
    assert value == weighted_variant("user-1", "refresh", variants)


def test_phase4_free_job_policy_blocks_code_background():
    allowed, reason, policy = evaluate_job_policy(
        plan="free",
        kind="project.code.patch",
        payload={"project_id": "p", "instruction": "x"},
        daily_count=0,
        active_count=0,
    )
    assert allowed is False
    assert reason
    assert policy["plan"] == "free"


def test_phase4_policy_enforces_variation_limit():
    allowed, reason, policy = evaluate_job_policy(
        plan="free",
        kind="image.variations",
        payload={"prompt": "x", "count": 4},
        daily_count=0,
        active_count=0,
    )
    assert allowed is False
    assert str(policy["image_variations_max"]) in reason


def test_phase4_job_payload_validation():
    value = validate_job_payload(
        "image.variations",
        {
            "prompt": "Premium NFC card",
            "preset": "product",
            "aspect_ratio": "16:9",
            "count": 9,
        },
    )
    assert value["count"] == 4
    assert value["prompt"] == "Premium NFC card"


def test_phase4_usage_costs_only_use_reported_signals():
    rows = [
        {
            "feature": "chat",
            "provider": "a",
            "status": "ok",
            "latency_ms": 100,
            "metadata": {"cost_usd": 0.1},
            "created_at": "2026-08-09T00:00:00+00:00",
        },
        {
            "feature": "image",
            "provider": "b",
            "status": "ok",
            "latency_ms": 200,
            "metadata": {},
            "created_at": "2026-08-09T01:00:00+00:00",
        },
        {
            "feature": "research",
            "provider": "c",
            "status": "429",
            "latency_ms": 300,
            "metadata": {"estimated_cost_usd": 0.2},
            "created_at": "2026-08-10T01:00:00+00:00",
        },
    ]
    value = summarize_usage_rows(rows)
    assert value["requests"] == 3
    assert value["cost"]["reported_cost_usd"] == 0.1
    assert value["cost"]["estimated_cost_usd"] == 0.2
    assert value["cost"]["unpriced_events"] == 1
    assert value["quota_429"] == 1


def test_phase4_routes_registered():
    paths = {path for route in app.routes if (path := getattr(route, "path", None))}
    expected = {
        "/api/platform/v9/snapshot",
        "/api/jobs/v9",
        "/api/notifications/v9",
        "/api/usage/v9",
        "/api/plan/policy/v3",
        "/api/features/v9/phase4",
        "/api/owner/platform/v9",
        "/health/v9-phase4",
    }
    assert expected.issubset(paths)
