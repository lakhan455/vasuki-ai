# Vasuki AI V11 — All-in-One Upgrade

V11 is designed to improve accuracy, autonomy, reliability and smoothness without adding dozens of permanent sidebar buttons. The optional `/v11` control center is a compact diagnostics/lab surface; normal Vasuki chat remains the main product UI.

## 1–35 implementation map

1. **Eval Engine V1** — 400 fixed cases across chat, coding, reasoning, research, RAG, vision, image and memory. `backend/scripts/run_v11_eval.py`; CI runs the contract suite on every `main` release.
2. **Automatic Answer Judge** — scores correctness signals, completeness, citation behavior, code quality and hallucination risk. Normal production chat is transparently judged after completion.
3. **Provider Quality Learning** — V9 telemetry/feedback remains active; V11 adds persisted benchmark/automatic-judge signals and task-aware learned ranking.
4. **Citation Fact Checker** — extracts important claims and checks lexical evidence support/coverage against supplied source snippets.
5. **Research Planner V3** — planner → parallel sub-question searches → evidence merge → explicit conflict resolution → cited synthesis.
6. **Autonomous Coding Agent V2** — analyze → project graph → plan → complete-file patch → validate → repair loop.
7. **Safe Code Execution Sandbox** — generated server code is never executed in the FastAPI/Render process. HTML/JS runs in a sandboxed browser iframe; Python runs in an isolated Pyodide Web Worker with timeout.
8. **Automatic Test-and-Fix Loop** — syntax validation plus bounded AI repair attempts; external/browser test errors can be fed into the next repair pass.
9. **GitHub Integration** — repo file read, issue read, compare, authorized branch/file-write/PR endpoints. Writes require one-time permission tokens.
10. **Project Knowledge Graph** — files, symbols, imports, API routes and SQL-table relationships; optional persistence per project.
11. **Memory Conflict Resolver V3** — active facts are deduplicated and newer facts supersede old active values.
12. **Temporal Memory** — `valid_from`, `valid_to`, `updated_at`, `supersedes`, active/superseded/deprecated states.
13. **Research Knowledge Base** — verified research reports can be saved project-wise with sources and verification metadata.
14. **Image Consistency Mode** — identity/product/logo lock prompt controls.
15. **Reference Image Controls** — optional reference image plus style, pose, composition and strength controls.
16. **Image Edit Mask/Brush UI** — brush mask in V11 UI; provider edit is composited back only through the selected mask.
17. **Video Generation Integration** — text→video and image→video gateway with duration/aspect/camera parameters. It activates when a compatible video provider is configured.
18. **Audio/TTS** — browser speech synthesis works without a new paid service; optional OpenAI-compatible server TTS is supported.
19. **Speech-to-Speech** — browser microphone → Vasuki → spoken browser answer.
20. **Multimodal Chat** — one request can combine text, images, PDFs/DOCX/TXT/MD/JSON/CSV and audio. Images use Vasuki Vision; PDFs use native extraction/vision fallback; audio uses server STT when configured.
21. **Agent Tools Framework** — controlled registry for web search, calculator, GitHub read, research and code graph.
22. **Permission System for Agents** — read tools are automatic; write/delete/send/deploy-style actions require exact one-time action+argument authorization.
23. **Scheduled Tasks/Reminders** — persistent one-time and recurring tasks with a scheduler loop.
24. **Reliability SLO Dashboard** — HTTP p50/p95, first-token p50/p95 from Vasuki chat telemetry, success/fallback/error percentages.
25. **Canary Releases** — deterministic owner/percentage release selection (`V11_CANARY_PERCENT`, default 5).
26. **Automatic Rollback** — health guard + rollback webhook. Real infrastructure rollback requires the webhook to be wired to the deployment platform.
27. **Database Performance Dashboard** — DB size, table scan/index health and slow-query signals when `pg_stat_statements` is available.
28. **Abuse/Fraud Protection** — request anomaly/rate guard and persistence schema for abuse events.
29. **Privacy Center** — V11 memory, research KB, schedules and retention visibility.
30. **Data Retention Policies** — per-user policies plus cleanup routines for V11 telemetry/permission/abuse data.
31. **Accessibility Audit** — static CI-friendly checks plus responsive/keyboard-friendly V11 controls. This is a baseline audit, not a substitute for a full screen-reader/axe manual certification.
32. **Internationalization** — V11 control surface ships en/hi/es/fr/de/ja locale labels. Legacy pages can migrate incrementally to the same registry.
33. **Mobile-first PWA Polish** — responsive V11 UI, PWA share target and file-handler manifest entries.
34. **OmniRoute Runtime Health UI** — Embedded Knowledge, Native Vasuki Providers, Sidecar, MCP and A2A are shown separately so embedded knowledge is never confused with live OmniRoute runtime.
35. **Capability Registry** — `/api/v11/capabilities` is the runtime source of truth instead of hard-coded frontend assumptions.

## Important production boundaries

- **No unsafe server code execution.** This is intentional. Running arbitrary generated code in the same Render process would be a security vulnerability.
- **Video generation is capability-gated.** Configure `V11_VIDEO_API_BASE_URL`, `V11_VIDEO_API_KEY` and optionally `V11_VIDEO_MODEL` for a compatible provider.
- **GitHub writes are capability-gated.** Configure a least-privilege `V11_GITHUB_TOKEN`; writes additionally require a one-time user authorization token.
- **Browser voice is immediately usable in supported browsers.** Server TTS/STT are optional.
- **Exact scheduled wake-ups on a sleeping free host cannot be guaranteed by the sleeping process itself.** Persistent tasks are safe; exact wake timing needs an external cron/always-on trigger.
- **Canary selection is implemented at application level.** True dual-deployment traffic splitting depends on your hosting layer.
- **Automatic rollback is implemented through a generic webhook.** It does not claim to control Vercel/Render unless that webhook is configured.
- **The 400-case release gate can run without spending provider quota in contract mode.** A live benchmark mode is available for configured environments.
- **Vision/image live eval quality needs actual media fixtures/providers.** The fixed suite still validates those capability contracts.
- **Citation checking is evidence-support scoring, not a mathematical proof of truth.** Research Planner V3 also forces evidence-only synthesis to reduce unsupported claims.

## New environment variables

```text
V11_EVAL_CONCURRENCY=3
V11_RESEARCH_MAX_SUBQUESTIONS=6
V11_CANARY_PERCENT=5
V11_ABUSE_REQUESTS_PER_MINUTE=120
V11_SCHEDULER_ENABLED=true
V11_SCHEDULER_POLL_SECONDS=60
V11_AUTO_ROLLBACK_ENABLED=false
V11_ROLLBACK_MIN_SAMPLES=50
V11_ROLLBACK_ERROR_PCT=12
V11_ROLLBACK_WEBHOOK_URL=
V11_MCP_ENABLED=false
V11_A2A_ENABLED=false

V11_GITHUB_TOKEN=

V11_VIDEO_API_BASE_URL=
V11_VIDEO_API_KEY=
V11_VIDEO_MODEL=auto

V11_TTS_API_BASE_URL=
V11_TTS_API_KEY=
V11_TTS_MODEL=tts-1

V11_STT_API_BASE_URL=
V11_STT_API_KEY=
V11_STT_MODEL=whisper-1
```

Never put backend tokens in Vercel/frontend variables.
