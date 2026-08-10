from app.main_v9_phase6 import app
from app.services.security_v9_phase6 import _fingerprint, _safe_metadata

def test_phase6_secret_fingerprint_never_returns_secret():
    secret = "super-secret-value-123"; value = _fingerprint(secret)
    assert value and secret not in value and len(value) == 16

def test_phase6_metadata_redacts_sensitive_keys():
    value = _safe_metadata({"safe":"ok","authorization":"Bearer abc","nested":{"private_key":"hidden","value":2}})
    assert value["safe"] == "ok" and value["authorization"] == "[redacted]" and value["nested"]["private_key"] == "[redacted]"

def test_phase6_routes_registered():
    paths = {getattr(route, "path", "") for route in app.routes}
    expected = {"/api/owner/security-center/v9","/api/owner/audit/v9","/api/owner/secrets/v9/rotation","/api/owner/backups/v9","/api/owner/backups/v9/{backup_id}/restore","/api/owner/errors/v9","/api/owner/release-health/v9","/api/owner/evals/v9","/health/v9-phase6"}
    assert expected.issubset(paths)
