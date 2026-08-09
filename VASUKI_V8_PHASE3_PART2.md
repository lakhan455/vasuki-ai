VASUKI AI V8 PHASE 3 PART 2

Added:
- Regenerate action for the latest normal text answer.
- Regeneration uses a fresh internal nonce so the simple-response cache cannot return the same cached wording.
- Edit & Resend for user prompts.
- Saved-chat edits/regenerations create a new saved branch so the original chat stays safe.
- Existing Phase 3 conversation-branch API stores branch metadata.
- Thumbs up/down now save real response feedback.
- Sidebar links: Projects, My Files, Image History, Owner Analytics (owner only).
- My Files, Image History, Owner Analytics and Projects pages now authenticate with the Supabase session and call the Render backend correctly.
- New /health/v8-phase3-part2 endpoint.

No new Supabase SQL migration is needed. Existing Phase 3 tables are reused.

Still pending after this Part 2 patch:
- hard backend provider-exclusion on regenerate,
- full branch-tree visual UI,
- project-memory injection into chat,
- semantic chat-history search.
