# Security checklist

- Revoke every credential ever pasted into chat, screenshots, tickets, or public repositories.
- Generate fresh credentials with the least required permissions.
- Never commit `.env` or `.env.local`.
- Keep all secret API calls in the FastAPI backend, never in browser JavaScript.
- Add provider spending caps, quotas, and alerts.
- Restrict Render `ALLOWED_ORIGINS` to the exact frontend domain.
- Rotate keys immediately if they appear in logs or Git history.
- Use a separate GitHub token only for deployment automation, with minimal repository scope.
