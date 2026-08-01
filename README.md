# Power Vasuki AI

A secure multi-provider AI web app with a **Next.js 16 frontend** and **FastAPI backend**.

## Features

- Chat provider fallback: Groq → Cerebras → SambaNova → Gemini → OpenRouter → Mistral
- Optional live web research: Tavily → Exa fallback
- Image generation: DeepAI → Hugging Face → Cloudflare Workers AI fallback
- OCR.Space upload endpoint
- Responsive ChatGPT-style interface
- API keys stay only in backend environment variables
- Render deployment config included

## Important security step

Do **not** use API keys that were pasted into chat or committed to Git. Revoke/rotate them first, then put only the new keys in local `.env` and hosting dashboards. Never upload `.env` to GitHub.

## Local setup on Windows PowerShell

### 1. Extract and open project

```powershell
cd "$HOME\Downloads\power-vasuki-ai"
```

### 2. Backend

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend test:

- Home: `http://localhost:8000`
- Swagger API docs: `http://localhost:8000/docs`

### 3. Frontend (new PowerShell window)

```powershell
cd "$HOME\Downloads\power-vasuki-ai\frontend"
Copy-Item .env.example .env.local
npm install
npm run dev
```

Open: `http://localhost:3000`

## Which keys are essential?

Start with only:

1. `GROQ_API_KEY` or `GOOGLE_GEMINI_API` for chat
2. `TAVILY_API_KEY` for live research
3. One image provider key for image generation

The rest are optional fallbacks. GitHub token should not be placed in this app's `.env`; use GitHub login/CLI separately.

## Deploy backend on Render

1. Push the complete project to GitHub as a **private repository**.
2. In Render, create a new Web Service from the repository.
3. Set Root Directory to `backend`.
4. Build command: `pip install -r requirements.txt`
5. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Add environment variables from `backend/.env.example` using fresh keys.
7. Set `ALLOWED_ORIGINS` temporarily to your future Vercel URL, or update it after frontend deployment.
8. Copy your Render URL, for example `https://power-vasuki-ai-api.onrender.com`.

## Deploy frontend on Vercel

1. Import the same GitHub repository into Vercel.
2. Set Root Directory to `frontend`.
3. Add environment variable:

```text
NEXT_PUBLIC_API_URL=https://YOUR-RENDER-BACKEND.onrender.com
```

4. Deploy. Vercel will give a public URL you can share with friends.
5. Return to Render and set `ALLOWED_ORIGINS` to that exact Vercel URL, then redeploy backend.

## Recommended production hardening

Before sharing widely, add authentication, per-user rate limits, daily quotas, abuse filtering, request logs without prompts/secrets, and billing limits on every API provider. API usage is not guaranteed to remain free.

## Project structure

```text
power-vasuki-ai/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── schemas.py
│   │   └── services/
│   ├── requirements.txt
│   ├── render.yaml
│   └── .env.example
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── package.json
│   └── .env.example
└── README.md
```
