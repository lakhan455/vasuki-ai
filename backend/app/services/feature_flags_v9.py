from __future__ import annotations
import hashlib, json, os

_DEFAULTS = {
    "research_v2": 100,
    "provider_quality_v2": 100,
    "citation_verifier": 100,
    "memory_policy_v2": 100,
    "eval_dashboard": 100,
}

def _config():
    raw = os.getenv("VASUKI_FEATURE_FLAGS_JSON", "").strip()
    if not raw:
        return dict(_DEFAULTS)
    try:
        data = json.loads(raw)
    except Exception:
        return dict(_DEFAULTS)
    out = dict(_DEFAULTS)
    for k, v in data.items():
        try:
            out[str(k)] = max(0, min(100, int(v)))
        except Exception:
            pass
    return out

def bucket(user_id: str, feature: str) -> int:
    return int(hashlib.sha256(f"{feature}:{user_id}".encode()).hexdigest()[:8], 16) % 100

def flags_for_user(user_id: str):
    cfg = _config()
    return {k: {"enabled": bucket(user_id, k) < v if v < 100 else True, "rollout_percent": v, "bucket": bucket(user_id, k)} for k, v in cfg.items()}
