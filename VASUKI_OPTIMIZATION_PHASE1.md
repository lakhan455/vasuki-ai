VASUKI AI OPTIMIZATION PHASE 1

Already present and not duplicated:
- SSE streaming, Stop/Abort
- context trimming
- parallel web/memory/document lookup
- pgvector document RAG + HNSW
- Supabase RLS + indexes
- per-minute/per-day quotas
- provider cooldown circuit breaker
- timeouts/graceful errors
- structured JSON logs
- file limits and Truth Guard

Added now:
- smart task/difficulty router
- short-hard code/math/logic -> strong tier
- max 3 provider attempts
- same-tier fallback
- Gemini buffered fallback
- provider health/latency scoring
- 429/quota-aware deprioritization
- request telemetry + estimated tokens
- response cache + separate web cache
- extractive older-context digest + latest 8 messages
- prompt-injection guard
- diagnostics endpoints
- router unit tests

Next phases after this one passes:
- persistent analytics + owner dashboard
- semantic pgvector personal memory
- permanent artifact storage + cleanup
- image prompt enhancer/router/queue
- file-specific pipelines
- chat pagination/index audit
- Free/Pro provider policy
- regenerate/edit-resend
- frontend dynamic imports + PWA
- 50-100 prompt quality harness
