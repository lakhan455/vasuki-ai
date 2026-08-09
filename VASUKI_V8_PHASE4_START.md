VASUKI AI V8 PHASE 4 START

Core additions:
- Real Project-specific Memory table with RLS and deduplication.
- Semantic project memory retrieval with Gemini embeddings + pgvector RPC.
- Lexical fallback when embeddings/RPC are unavailable.
- Active project context injection into the existing V8 private-context pipeline.
- ChatRequest now accepts optional project_id.
- Saved chats can be associated with a project.
- Main chat UI gets an active Project selector.
- Chat-history search searches saved titles and message content.
- Branch Explorer page lists recent Edit & Resend / Regenerate branches.
- Projects page now lets the user create and delete project memories.
- New /health/v8-phase4 endpoint.

Phase 4 Start does not yet include:
- automatic extraction of project memories from every conversation,
- project-memory conflict resolution UI,
- fully semantic chat-history embeddings,
- graphical branch tree edges,
- per-project file attachment scoping.
