# Vasuki AI V9 Phase 4

Scope: roadmap items 23-30.

## Implemented

23. Background job queue
- Supabase-persisted `background_jobs_v9`.
- Atomic PostgreSQL `FOR UPDATE SKIP LOCKED` claim function with stale-running recovery after worker restarts.
- Render process worker with coarse progress updates.
- Background handlers for image generation, image variations and project coding-plan jobs.

24. Job progress UI
- New `/operations` Operations Center.
- Live polling, progress bars, status/error display and pending-job cancellation.

25. Notification center
- Persistent `notifications_v9`.
- Job success/failure notifications.
- Unread count, mark-one-read and mark-all-read.

26. User usage dashboard
- 30-day request counts, feature/provider usage, latency, errors and quota-429 counts in Operations Center.

27. Owner cost/quota dashboard
- `/owner` upgraded with jobs, quota errors, provider usage, experiments and cost signals.
- No provider price is invented. Exact/estimated costs are shown only when usage metadata contains `cost_usd` or `estimated_cost_usd`.

28. Plan Policy Engine V3
- Free/Pro/Owner background-job daily limits, active-job limits and job-kind allowlists.
- `VASUKI_PLAN_POLICY_JSON` can override defaults.
- Enforcement is wired to V9 background job submission.

29. Feature Flags V3
- Defaults + environment override + Supabase database override.
- Kill switch, deterministic rollout percent and owner toggle UI.
- `VASUKI_FEATURE_FLAGS_V3_JSON` supported.

30. A/B testing
- Weighted deterministic variants with explicit exposure and conversion events.
- Exposure/conversion event table and endpoints.
- Operations Center refresh cadence is a real 50/50 control-vs-fast experiment.

## Important boundaries

- Phase 4 does not force-cancel a provider call that is already running. Pending jobs can be cancelled.
- Job persistence and atomic claiming are production-oriented, but the worker still runs inside the Render web service; a dedicated worker service can be introduced later if workload volume grows.
- Background project coding jobs generate plans/diffs only. They retain Phase 2 safety boundaries and do not execute arbitrary server-side code.
- Cost dashboard is observability, not billing. Unknown provider costs remain explicitly unpriced.
- Plan Policy V3 is enforced for new V9 background jobs. It does not retroactively gate every legacy synchronous endpoint.
