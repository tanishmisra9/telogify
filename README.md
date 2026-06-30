# Telogify

F1 telemetry intelligence. Ingests a full FastF1 race weekend and produces **3 quantified, telemetry-grounded insights**, delivered as a web page and a post-race email digest.

The core principle is **zero quantitative hallucination**: a deterministic backend computes every number and stores it in Postgres; a LangGraph ReAct agent (Claude Opus) retrieves exact values via bound tools and writes prose around them. No number is ever invented by the model.

## Stack

- **Backend:** Python, FastAPI, LangGraph, SQLModel + Alembic, Postgres, Anthropic SDK, FastF1, Resend, pytest
- **Frontend:** Vite + React + TypeScript + Tailwind + Framer Motion
- **Infra:** Railway (backend + Postgres) + Vercel (frontend)

## Quickstart (backend)

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
cp .env.example .env   # fill in secrets
telogify --help
```

## CLI

```bash
telogify run-weekend <year> <round>   # ingest + compute + generate 3 insights
telogify diagnose <year> <round>      # ranking sanity: clean-lap counts, confidence
telogify send-digest <year> <round>   # email the 3 insights
```

Full setup, env vars, migrations, and deploy notes land in M21.
