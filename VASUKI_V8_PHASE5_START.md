VASUKI AI V8 PHASE 5 START

Implemented in this start:
- Smart Regenerate V2:
  - real response-cache bypass
  - previous-provider family exclusion when another healthy provider is available
  - safe fallback to the original family if no alternative exists
- Normal active-project chat now sends project_id to the Vasuki backend.
- Automatic Project Memory capture:
  - high-precision explicit project facts/instructions
  - no extra LLM call
  - existing sensitive-data guard + deduplication reused
  - saved with source "auto-chat" and confidence 0.90
- Deep Research V2 page at /research:
  - forces live web/current routing
  - stronger research prompt
  - source cards
  - optional active project context
- Live Code Lab at /code:
  - HTML/CSS/JavaScript editor
  - live sandboxed iframe preview
  - manual/auto run
  - copy combined HTML
  - downloadable HTML
- New /health/v8-phase5 endpoint.
- No new Supabase migration is required for this Phase 5 Start.

Still pending for Phase 5 Part 2+:
- semantic embeddings for full chat-history search
- AI-generated code diff + one-click apply-to-workspace
- graphical branch tree
- automatic conflict resolver UI for project memories
- per-project file scoping
- multi-pass research planner / researcher / verifier pipeline
