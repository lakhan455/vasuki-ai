# Vasuki AI V9 Phase 5

Scope: roadmap items 32-42.

## Implemented

32. Chat export
- Saved chats can be exported as Markdown or JSON from `/account`.

33. Full account export
- Authenticated JSON export across user-scoped Vasuki tables.
- Derived embeddings and secret-like fields are intentionally redacted.

34. Account delete flow
- Exact confirmation phrase + matching account email.
- Deletes user-scoped content/storage before Supabase Auth deletion.
- Owner self-service deletion is blocked.

35. File storage quotas
- Free: 250 MB, Pro: 2 GB, Owner: 20 GB by default.
- Counts generated artifacts, knowledge documents and Project KB files.
- Overrides supported with `VASUKI_STORAGE_QUOTAS_JSON`.
- Quota checks are patched into artifacts, Knowledge/RAG uploads and Project KB uploads.

36. Auto cleanup
- Hourly backend maintenance cleans expired generated artifacts.
- User can manually clean expired generated files from `/account`.

37. PWA
- Next.js manifest, service worker, install prompt support and app icon.

38. Push notifications
- Web Push subscription storage and service worker push handling.
- Existing in-app notification creation is extended to Web Push when VAPID is configured.
- Requires `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, and optional `VAPID_SUBJECT`.

39. Offline UI
- Network-first cached navigation shell and dedicated `/offline` fallback.
- AI calls still require network.

40. Keyboard shortcuts
- Ctrl/Cmd+K command palette.
- Alt+N new chat, Alt+O Operations, Alt+A Account.

41. Command Palette
- Global accessible command dialog with navigation and PWA install action.

42. Accessibility
- Skip link, strong focus-visible styling, reduced-motion support, forced-colors support,
  semantic dialog roles and live offline status.

## Important boundaries

- Full account export is user-data oriented; derived embeddings and secret-like fields are redacted.
- Account deletion is irreversible and intentionally requires two confirmations.
- PWA offline mode caches the UI shell, not model/provider responses.
- Browser Push is implemented but remains disabled until VAPID keys are configured in Render.
- Storage quota enforcement covers the main persistent file paths currently used by Vasuki AI.
