# Corvo PR-to-PO (Cantill.ai full-stack task)

A policy-driven purchase-requisition-to-PO web app for the fictional Corvo Engineering.

- `engine/`: pure Python decision engine. Every limit, window, count, weight and the rule order come from the
  policy JSON (`engine/policies/policy_v5_0.json`). A new policy version changes decisions with no code change.
- `api/`, `services/`, `db/`: FastAPI backend, PostgreSQL via SQLAlchemy + Alembic (SQLite for local runs and tests).
- `frontend/`: React (Vite + Tailwind) screens: chat intake, batch upload, buyer workspace, policy amendments,
  contracts, preferred suppliers.
- LLM: OpenRouter (OpenAI-compatible API, model from `OPENROUTER_MODEL`). Chat extraction, amendment reading and
  contract-PDF fallback use it; each has a rule-based fallback, so the app works without a key.

Design and decisions: [APPROACH.md](APPROACH.md), [DECISIONS.md](DECISIONS.md).

## Run with Docker (one command)

```bash
cp .env.example .env        # then put your key in OPENROUTER_API_KEY (optional)
docker compose up --build
```

- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs, health: http://localhost:8000/api/health

The backend container runs `alembic upgrade head`, seeds an empty database (kit CSVs, the two PDF-only contracts,
policy v5.0 ACTIVE) and starts uvicorn. Compose reads `.env` for variable substitution; `.env` is gitignored.

## Local development without Docker

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
$env:DATABASE_URL = "sqlite:///./corvo.db"
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m seed.load --if-empty
.venv\Scripts\python -m uvicorn api.main:app --port 8000
# second shell
cd frontend; npm install; npm run dev     # http://localhost:5173, /api proxied to :8000
```

The backend loads `.env` itself (python-dotenv, real environment variables win). `GET /api/health` reports
`llm: enabled` and the model when a key was found; the key is never logged or returned. The UI header shows
"AI: on/off". Set `LLM_DISABLED=1` to force the rule-based fallbacks.

## Tests

```powershell
.venv\Scripts\python -m pytest
```

No test uses the network (`LLM_DISABLED=1`). API tests build a seeded SQLite database with Alembic.
Engine golden tests cover the 14 worked examples, 3 rankings and the policy-change proof tests a-h.

## Batch API

```bash
curl -F file=@pr_batches/sample_pr_batch.csv http://localhost:8000/api/process-batch                 # JSON
curl -F file=@pr_batches/sample_pr_batch.csv "http://localhost:8000/api/process-batch?format=csv" -o out.csv
curl -F file=@batch.csv -F policy_version=5.1 -F as_of=2026-11-20 "http://localhost:8000/api/process-batch?format=csv"
```

CSV columns: `pr_no, pr_line, resolved_item_code, group_id, po_id, decision, route, supplier_id, unit_price,
group_value_inr, suggested_supplier_ids (; separated), policy_version, reason`. Rejected lines have route
`NOT_PROCESSED` and a reason. Without a pin, each line uses the latest approved version effective on its
creation date (or on `as_of`).

Preferred-supplier export: `GET /api/preferred-suppliers/export?as_of=YYYY-MM-DD` (item_code, rank, supplier_id,
reference_price; top 3 per item as set by the policy).

## Blind-test playbook

1. Run 1: Batch upload screen, choose the new batch, pin "Process under v5.0", Process batch, Download CSV.
2. Policy screen: upload the amendment (PDF/DOCX/TXT) or describe it. Review the plain-language bullets, errors and
   the dry run ("N of M lines change"), set or confirm the effective date, Approve and activate.
3. Run 2: process the same batch pinned to the new version (an effective date after the PR dates would otherwise
   keep v5.0 for those lines), Download CSV.
4. Preferred suppliers screen: set the as-of date, Export CSV.

## Deploy to Render (prepared, not deployed)

`render.yaml` defines a free PostgreSQL database, the Docker backend (`/api/health` health check) and the static
frontend.

1. Push this repository to GitHub (the kit data folders are already tracked; `.env` and `open-router.txt` are not).
2. In Render: New > Blueprint, pick the repository, apply.
3. Set `OPENROUTER_API_KEY` on `corvo-backend` (it is `sync: false`, so Render asks for it).
4. If Render gives the services different URLs, update `CORS_ORIGINS` (backend) and `VITE_API_BASE`
   (frontend, the backend URL + `/api`) and redeploy the frontend.
5. Open the frontend URL. Free instances sleep after inactivity; open `/api/health` a minute before a demo.

Railway alternative: create a PostgreSQL plugin, a service from the repo root Dockerfile with `DATABASE_URL`
(Railway's `postgresql://` URL is converted to the psycopg driver automatically), `OPENROUTER_API_KEY`,
`CORS_ORIGINS`, and a second service from `frontend/` with build arg `VITE_API_BASE=https://<backend>/api`.

## Identity

The user selector in the header sends `X-User` / `X-Role` headers (requester, buyer, procurement). Buyers approve
and override requirements; procurement approves policy versions. This is a stub, not real authentication.

## Open items

- D60: the worked examples' PO numbers are one lower than the policy produces; tests check relative numbering.
