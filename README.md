# Telogify

F1 telemetry intelligence. Ingests a full FastF1 race weekend (all sessions) and produces
**3 quantified, telemetry-grounded insights**, delivered as a web page and a post-race
email digest. The insights are the product.

## Core principle: zero quantitative hallucination

A deterministic backend computes every number (corner deltas, straight speeds, stint pace,
finishing gaps) and stores it in Postgres. The insight engine is a LangGraph ReAct agent
(Claude Opus) with bound tools that query Postgres. The model never invents a number; it
retrieves exact values via tool calls and writes prose around them. Every number in a
published insight is traceable to a logged tool return in `source_tool_calls_json`.

```
PreCompute (deterministic, all sessions)
  ingest -> corners -> straights -> stints -> results
  -> fingerprints -> attributions -> constructor index -> candidate insights (ranked)
        -> InsightAgent (LangGraph ReAct, Opus + bound DB tools) -> 3 insights
        -> web page + Resend email digest
```

## Stack

- **Backend:** Python 3.12, FastAPI, LangGraph, SQLModel + Alembic, Postgres, Anthropic SDK
  (`claude-sonnet-5`), FastF1, Resend, pytest. Manual CLI trigger only (no scheduler).
- **Frontend:** Vite + React + TypeScript + Tailwind v4 + Framer Motion. Custom SVG charts (no
  chart library). Vitest for unit tests.
- **Infra:** Railway (backend + Postgres), Vercel (frontend).

## Backend setup

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
cp .env.example .env            # fill in secrets (see below)

# local Postgres (Homebrew postgresql@16)
createdb telogify_dev && createdb telogify_test
alembic upgrade head            # apply migrations to telogify_dev
```

### Environment variables (`backend/.env`)

| Var | Purpose |
| --- | --- |
| `DATABASE_URL` | Postgres URL. Local default `postgresql://localhost:5432/telogify_dev`. `postgres://` is auto-normalized. |
| `ANTHROPIC_API_KEY` | Required by the insight agent. The agent fails loud if it is missing. |
| `ANTHROPIC_MODEL` | Defaults to `claude-sonnet-5`. |
| `RESEND_API_KEY` | Required by `send-digest`. Pre-domain, uses Resend's shared sender. |
| `RESEND_FROM` | Sender, e.g. `Telogify <insights@telogify.app>` once the domain is verified. |
| `FASTF1_CACHE` | FastF1 on-disk cache dir (default `.fastf1_cache`). |
| `WEB_BASE_URL` | Base URL the email CTA links to. |

### CLI

```bash
telogify run-weekend 2025 11    # ingest + compute + generate and persist 3 insights
telogify run-weekend 2026       # all completed rounds for the season (one agent call per weekend)
telogify run-weekend 2026 --dry-run  # preview which rounds would run, no API spend
telogify diagnose 2025 11       # ranking sanity: clean-lap counts + attribution confidence
telogify send-digest 2025 11    # email the 3 insights to subscribers via Resend
```

### Migrations

```bash
alembic revision --autogenerate -m "message"   # after changing models.py
alembic upgrade head
```

### Tests

```bash
pytest        # requires telogify_test to exist; tests create/drop their own tables
```

### API (local)

```bash
uvicorn telogify.api.main:app --reload    # http://localhost:8000
```

## Frontend setup

```bash
cd frontend
npm install
cp .env.example .env     # set VITE_API_URL if the backend is not on localhost:8000
npm run dev              # http://localhost:5173
npm run build            # production build to dist/
npm test                 # vitest unit tests (pure lib functions)
```

Four routes: landing (`/`), weekends index (`/weekends`), race weekend page
(`/weekends/:year/:round`: 3 insights + pace/degradation charts + finishing order), and
subscribe (`/subscribe`).

## Deploy

**Backend (Railway):** create a project, add the Postgres plugin (injects `DATABASE_URL`),
and point a service at this repo with root directory `backend`. `backend/railway.toml`
runs `alembic upgrade head` then `uvicorn` on deploy. Set `ANTHROPIC_API_KEY`,
`RESEND_API_KEY`, `RESEND_FROM`, and `WEB_BASE_URL` in the service variables.

**Frontend (Vercel):** import the repo with root directory `frontend` (Vite is
auto-detected, output `dist`). `frontend/vercel.json` rewrites all routes to `index.html`
for client-side routing. Set `VITE_API_URL` to the Railway backend URL.

No CI yet.

## Validation

```bash
telogify run-weekend 2025 11   # Austrian GP; persists 3 insights with traceable numbers
telogify diagnose 2025 11      # sane clean-lap counts, no mid-field team buried
telogify send-digest 2025 11   # well-formed email with the 3 insights and a working CTA
```
