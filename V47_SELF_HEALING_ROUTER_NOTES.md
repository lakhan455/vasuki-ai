# Vasuki AI V47 — Self-Healing Persistent Reliability Router

V47 upgrades the V46 adaptive-speed layer into the production chat path used by Vasuki AI on Render.

## What changed

- Production `chat_v7` routing now uses a V47 runtime reliability layer.
- Runtime provider speed/reliability is learned per task type.
- Sampled learning is restored after restart from the existing `v11_provider_quality` Supabase table.
- No new SQL migration is required when the existing V11 schema is already deployed.
- Repeated provider failures open a task-specific exponential circuit breaker.
- Provider first-token timeout adapts to that provider's learned latency.
- Existing V12/V13 quality ranking remains the anchor; V47 only reorders inside a small quality band.
- Provider racing is still disabled, so V47 does not create duplicate paid provider requests.
- Existing V45 diagnostics are preserved and extended with `router_version` and `reliability_score`.
- V46 remains available and its health endpoint is unchanged.

## New health / diagnostics

- `GET /health/v47`
- Authenticated owner endpoint: `GET /api/owner/v47/providers/reliability`

## New settings (all optional)

```text
V47_RELIABILITY_ROUTER_ENABLED=true
V47_PERSISTENT_LEARNING_ENABLED=true
V47_ADAPTIVE_MIN_SAMPLES=2
V47_PERSIST_EVERY_N_SUCCESSES=3
V47_PERSIST_TIMEOUT_SECONDS=1.2
V47_RESTORE_TIMEOUT_SECONDS=4.0
V47_CIRCUIT_FAILURE_THRESHOLD=2
V47_CIRCUIT_BASE_COOLDOWN_SECONDS=45
V47_CIRCUIT_MAX_COOLDOWN_SECONDS=900
V47_FIRST_TOKEN_TIMEOUT_FLOOR_SECONDS=1.0
V47_SIMPLE_FIRST_TOKEN_TIMEOUT_MAX_SECONDS=3.5
V47_CODE_FIRST_TOKEN_TIMEOUT_MAX_SECONDS=5.5
V47_LARGE_FIRST_TOKEN_TIMEOUT_MAX_SECONDS=7.0
```

Defaults are already included in `backend/app/config.py`; you do not need to add these variables to Render unless you want to override them.

## Compatibility / validation

- Render entrypoint remains `uvicorn app.main_v11:app`.
- No new API key required.
- No new Python dependency required.
- No provider racing / duplicate request behavior introduced.
- Full backend regression result during package creation: **266 passed**.
- Import smoke test confirmed `/health/v47` and `/api/owner/v47/providers/reliability` are registered.
