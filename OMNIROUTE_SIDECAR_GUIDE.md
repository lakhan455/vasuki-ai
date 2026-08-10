# OmniRoute v3.8.50 Sidecar Setup for Vasuki V10

This guide is derived from the supplied `OmniRoute-release-v3.8.50.zip`.

Vasuki V10 can run without the sidecar, but the full OmniRoute provider/combo engine becomes active only when this runtime is reachable.

## Source requirements

From `package.json`:

- Node: `>=22.22.2 <23 || >=24.0.0 <27`
- Version: `3.8.50`
- Build: `node scripts/build/build-next-isolated.mjs`
- Start: `node scripts/dev/run-next.mjs start`

From the supplied Docker guide:

- documented gateway/dashboard port: `20128`
- OpenAI-compatible surface: `/v1/*`
- persistent data should live under `/app/data` in Docker
- Redis backs distributed rate limiting/shared cache in the supplied Compose stack; disabling it degrades to in-memory behavior
- production Docker needs `OMNIROUTE_WS_BRIDGE_SECRET`
- `runner-base` is the minimal production target; `runner-cli` adds provider/agent CLIs

## Local extraction

Run the included `prepare-omniroute-sidecar.ps1`. It only extracts the archive; it does not execute third-party code.

After extraction, review `.env.example`, provider terms, and the Docker guide before starting the runtime.

## Recommended production shape

Keep two services:

1. **Vasuki FastAPI** — user auth, memory, projects, research, documents, policies, account/security.
2. **OmniRoute** — provider connections, combos, `auto/*` routing, account/quota/cost/circuit-breaker logic and protocol translation.

Point Vasuki's backend-only `OMNIROUTE_BASE_URL` to the OmniRoute service and use a private OmniRoute API key.

## Security

- Do not expose OmniRoute management APIs without authentication.
- Do not expose Redis publicly without authentication.
- Do not put provider credentials or `OMNIROUTE_API_KEY` in Vercel/frontend.
- Web/session-cookie providers in the supplied source require provider-specific terms review before public/commercial use.
