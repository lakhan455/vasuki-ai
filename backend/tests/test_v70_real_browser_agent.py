from pathlib import Path

from app.v70.browser_agent import (
    host_intrinsically_blocked,
    interaction_policy,
    normalize_start_url,
)


def test_v70_normalizes_public_url_from_goal():
    assert (
        normalize_start_url(
            "Open https://example.com/docs and inspect it"
        )
        == "https://example.com/docs"
    )
    assert (
        normalize_start_url(
            "Check example.com/pricing"
        )
        == "https://example.com/pricing"
    )


def test_v70_blocks_private_and_loopback_hosts():
    assert host_intrinsically_blocked("localhost") is True
    assert host_intrinsically_blocked("127.0.0.1") is True
    assert host_intrinsically_blocked("10.0.0.8") is True
    assert host_intrinsically_blocked("169.254.169.254") is True
    assert host_intrinsically_blocked("example.com") is False


def test_v70_interactions_require_approval_and_secrets_are_blocked():
    click = interaction_policy(
        {
            "action": "click",
            "reason": "open details",
        },
        {
            "type": "",
            "text": "View details",
        },
    )
    assert click["allowed"] is True
    assert click["approval_required"] is True

    password = interaction_policy(
        {
            "action": "fill",
            "reason": "login",
        },
        {
            "type": "password",
            "text": "Password",
        },
    )
    assert password["allowed"] is False

    payment = interaction_policy(
        {
            "action": "click",
            "reason": "checkout",
        },
        {
            "type": "",
            "text": "Pay now",
        },
    )
    assert payment["allowed"] is False


def test_v70_production_wiring_present():
    repo = Path(__file__).resolve().parents[2]

    main_v11 = (
        repo
        / "backend/app/main_v11.py"
    ).read_text(
        encoding="utf-8"
    )

    api = (
        repo
        / "frontend/lib/api.ts"
    ).read_text(
        encoding="utf-8"
    )

    chat = (
        repo
        / "frontend/components/ChatApp.tsx"
    ).read_text(
        encoding="utf-8"
    )

    requirements = (
        repo
        / "backend/requirements.txt"
    ).read_text(
        encoding="utf-8"
    )

    assert '"/health/v70"' in main_v11
    assert '"/api/v70/browser/jobs"' in main_v11
    assert "v70_create_browser_job" in main_v11
    assert "startBrowserJobV70" in api
    assert "approveBrowserJobV70" in api
    assert "cancelBrowserJobV70" in api
    assert "isLikelyBrowserWorkRequestV70" in chat
    assert "playwright" in requirements.casefold()


def test_v70_does_not_fake_browser_availability():
    source = (
        Path(__file__).resolve().parents[1]
        / "app/v70/browser_agent.py"
    )
    text = source.read_text(
        encoding="utf-8"
    )

    assert '"ready": ready' in text
    assert "chromium_installed" in text
    assert "fake_ready_state_allowed" in text
    assert '"fake_ready_state_allowed": False' in text
