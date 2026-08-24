from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    incident_type: str
    retry_same_provider: bool
    switch_provider: bool
    suggested_provider: str | None
    cooldown_seconds: int
    user_action: str
    safe_to_auto_retry: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def provider_family(name: str) -> str:
    value = str(name or "").strip().casefold()
    if value in {"groq", "groq_fast"}:
        return "groq"
    return value


def classify_incident(error: str) -> str:
    text = str(error or "").casefold()
    if re.search(r"\b(?:401|403|unauthori[sz]ed|invalid api key|invalid token|authentication)\b", text):
        return "auth"
    if re.search(r"\b(?:quota|credits? depleted|resource_exhausted|insufficient credits|billing)\b", text):
        return "quota"
    if re.search(r"\b(?:429|rate limit|too many requests)\b", text):
        return "rate_limit"
    if re.search(r"\b(?:timeout|timed out|deadline exceeded)\b", text):
        return "timeout"
    if re.search(r"\b(?:connection reset|dns|network|connecterror|connection refused)\b", text):
        return "network"
    if re.search(r"\b(?:flagged|moderation|safety policy|content policy)\b", text):
        return "moderation"
    if re.search(r"\b(?:400|422|invalid request|validation error|unevaluated properties|bad request)\b", text):
        return "invalid_request"
    return "unknown"


def recovery_plan(
    provider: str,
    error: str,
    candidates: list[str] | tuple[str, ...] = (),
) -> RecoveryPlan:
    incident = classify_incident(error)
    current_family = provider_family(provider)
    alternatives = [
        item
        for item in candidates
        if item and provider_family(item) != current_family
    ]
    suggested = alternatives[0] if alternatives else None

    if incident == "auth":
        return RecoveryPlan(incident, False, bool(suggested), suggested, 0, "verify or rotate the provider credential in server secrets", False)
    if incident == "quota":
        return RecoveryPlan(incident, False, bool(suggested), suggested, 0, "check provider quota/billing; use a configured fallback meanwhile", False)
    if incident == "rate_limit":
        return RecoveryPlan(incident, False, bool(suggested), suggested, 60, "wait for the rate-limit window or use a healthy fallback", True)
    if incident in {"timeout", "network"}:
        return RecoveryPlan(incident, True, bool(suggested), suggested, 2, "retry once, then fail over if latency remains unhealthy", True)
    if incident == "moderation":
        return RecoveryPlan(incident, False, False, None, 0, "review the request and provider policy; do not auto-bypass safety filtering", False)
    if incident == "invalid_request":
        return RecoveryPlan(incident, False, bool(suggested), suggested, 0, "inspect request payload/model parameters before retrying", False)
    return RecoveryPlan(incident, True, bool(suggested), suggested, 1, "retry once with diagnostics, then switch provider if available", True)
