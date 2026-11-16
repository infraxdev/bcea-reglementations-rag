# BCEAO RAG Tester

Minimal Next.js interface for exercising the FastAPI RAG backend (`app/main.py`) directly:
send a query, see the answer, inspect the retrieved sources/scores, and see when the
query router or policy gate stepped in. Also lets you override the generation
provider/model per-request to A/B ollama vs. openai vs. anthropic without restarting
the backend (mirrors `POST /query`'s `provider`/`model` fields).

## Setup

```bash
npm install
cp .env.local.example .env.local   # point at the backend, if not localhost:8000
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The backend must be running
separately (see the repo root `README.md`) and must allow this origin via
`CORS_ALLOWED_ORIGINS` (defaults to `http://localhost:3000` already).

## Container (production)

The app is a static export (`output: "export"`), so `npm run build` writes plain files
to `out/`. `Dockerfile` serves them with nginx on port 8080 and proxies `/api/*` to the
backend, so the browser stays on one origin and CORS isn't needed:

```bash
docker build -t bceao-rag-web .
docker run -p 8080:8080 -e API_UPSTREAM=http://host.docker.internal:8000 bceao-rag-web
```

On EKS, `API_UPSTREAM` defaults to `http://api` (the `api` Service). See
`infra/kubernetes/apps/web` and `docs/aws-architecture.md` §5.

## Structure

- `app/` — Next.js App Router entry (`layout.tsx`, `page.tsx`).
- `components/chat/` — the conversation UI (message list/bubbles, source citations, input).
- `components/settings/` — provider/model override control.
- `lib/api.ts` — fetch wrapper for the backend's `/query` endpoint.
- `lib/types.ts` — TypeScript mirrors of the backend's Pydantic request/response models.
