# Vasuki V10 Omni Brain — Render Environment Checklist

Set these only on the **Vasuki backend Render service**, never in the frontend/Vercel:

```text
OMNIROUTE_ENABLED=true
OMNIROUTE_BASE_URL=https://YOUR-OMNIROUTE-SERVICE
OMNIROUTE_API_KEY=YOUR_PRIVATE_GATEWAY_KEY
OMNIROUTE_TIMEOUT_SECONDS=65
OMNIROUTE_COMPRESSION=default
OMNIROUTE_BUDGET_USD=0
OMNIROUTE_BUDGET_FALLBACK=cheapest
OMNIROUTE_KNOWLEDGE_ENABLED=true
OMNIROUTE_SEARCH_ENABLED=false
OMNIROUTE_IMAGE_ENABLED=false
OMNIROUTE_IMAGE_MODEL=
OMNIROUTE_EMBEDDING_ENABLED=false
OMNIROUTE_EMBEDDING_MODEL=
```

Do not paste `OMNIROUTE_API_KEY` into chat, Git, screenshots or logs.

Enable image/embedding routing only after the exact compatible models are connected in the OmniRoute dashboard.
