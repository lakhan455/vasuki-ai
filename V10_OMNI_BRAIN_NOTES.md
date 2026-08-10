# Vasuki AI V10 — Omni Brain

Source archive reviewed: `OmniRoute-release-v3.8.50.zip`.

This integration keeps Vasuki AI as the product/backend of record and adds OmniRoute as an optional routing sidecar. It does **not** replace Vasuki memory, projects, research, documents, account controls, security, or the V9 fallback router.

## What is implemented

- Source-derived OmniRoute knowledge corpus:
  - 394 canonical/key implementation files indexed.
  - 6625 searchable chunks.
  - Canonical English docs plus routing/combo/guardrail/usage/provider implementation areas.
  - Translations/tests excluded to avoid duplicate/noisy knowledge.
- Automatic chat routing when the sidecar is configured:
  - simple -> `auto/fast`
  - general -> `auto`
  - code -> `auto/coding:reliable`
  - reasoning -> `auto/reasoning:reliable`
  - research/current -> `auto/reasoning:reliable`
- Per-request OmniRoute controls:
  - `X-OmniRoute-Mode`
  - optional strict/cheapest budget fallback
  - compression override
  - cache bypass propagation
  - disables OmniRoute memory injection because Vasuki already owns personal/project memory.
- Automatic fallback to Vasuki's existing V7/V9 router if the OmniRoute gateway is missing or fails.
- Partial-stream recovery: if the sidecar fails after emitting text, Vasuki resumes locally instead of blindly restarting.
- Optional web-search supplementation through `/v1/search` when Vasuki research evidence is sparse.
- Optional image generation through `/v1/images/generations`, with existing Vasuki image routing fallback.
- Optional embeddings through `/v1/embeddings`, with Gemini embedding fallback and dimension verification.
- Owner status endpoint: `/api/owner/omni/v10`.
- Knowledge endpoints:
  - `/api/omni/v10/knowledge`
  - `/api/omni/v10/knowledge/search`
- Health endpoint: `/health/v10-omni`.
- OmniRoute MIT notice preserved in `THIRD_PARTY_NOTICES/OmniRoute-LICENSE.txt`.

## Important runtime truth

The large provider catalog, account pools, 13-factor auto scoring, circuit breakers, connection cooldowns, model lockouts, quota/cost accounting, MCP, A2A and provider translators live in the **OmniRoute runtime**. They become active for Vasuki only after a reachable OmniRoute service is deployed and providers are connected there.

Without that sidecar, V10 remains safe: the OmniRoute knowledge corpus is available and chat/image/embeddings fall back to Vasuki's existing production paths.

## Render environment variables for Vasuki backend

Required to turn on the gateway:

- `OMNIROUTE_ENABLED=true`
- `OMNIROUTE_BASE_URL=https://YOUR-OMNIROUTE-SERVICE`
- `OMNIROUTE_API_KEY=...` (recommended for any remote/public OmniRoute service; never put this in Vercel/frontend)

Optional:

- `OMNIROUTE_TIMEOUT_SECONDS=65`
- `OMNIROUTE_COMPRESSION=default`
- `OMNIROUTE_BUDGET_USD=0` (0 = no per-request budget header)
- `OMNIROUTE_BUDGET_FALLBACK=cheapest` (`strict` hard-blocks over-budget selection)
- `OMNIROUTE_KNOWLEDGE_ENABLED=true`
- `OMNIROUTE_SEARCH_ENABLED=false`
- `OMNIROUTE_IMAGE_ENABLED=false`
- `OMNIROUTE_IMAGE_MODEL=` (must be an image model actually configured in OmniRoute)
- `OMNIROUTE_EMBEDDING_ENABLED=false`
- `OMNIROUTE_EMBEDDING_MODEL=` (must support the configured Vasuki embedding dimension)

## OmniRoute runtime requirements from the supplied source

`package.json` version: `3.8.50`.

Node engine:
`>=22.22.2 <23 || >=24.0.0 <27`

Primary scripts:
- dev: `node --max-old-space-size=8192 scripts/dev/run-next.mjs dev`
- build: `node scripts/build/build-next-isolated.mjs`
- start: `node scripts/dev/run-next.mjs start`

Default documented gateway port is 20128 and the OpenAI-compatible base is `/v1`.

## Do not enable blindly

The supplied source documents web/session-cookie and free-provider paths. For a public hosted Vasuki service, review each provider's terms and auth method before enabling it. Prefer official/API-compatible provider connections for production.
