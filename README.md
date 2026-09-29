# AI Deal Intelligence & Win-Loss Recommender

A B2B sales intelligence application that analyses open opportunities, explains
why comparable deals were won or lost, and produces evidence-backed next-action
recommendations. PostgreSQL is the source of truth; **Hindsight** is the
contextual memory layer that remembers what happened on each account and why.

- Hindsight repository: https://github.com/vectorize-io/hindsight
- Hindsight docs: https://hindsight.vectorize.io/
- What is agent memory: https://vectorize.io/what-is-agent-memory

---

## Architecture

```
React + TypeScript (Vite)  ──►  FastAPI  ──►  PostgreSQL        source of truth
        :5173 dev               :8000       :5432              (deals, users, events)
                                          └─►  Hindsight :8888  contextual memory (per-org bank)
                                          └─►  Ollama    :11434 local LLM (llama3.2:3b)
```

Design rules that the code enforces:

- **PostgreSQL owns the records.** Hindsight never becomes the system of record.
- **Per-organisation isolation.** Every memory is written to bank `org-<organization_id>`
  and tagged with `organization_id` metadata; the API only ever queries its own bank.
- **Recommendations cite real records.** Actions produced by the LLM are validated
  against evidence actually returned by the similarity engine and discarded if they
  cannot be tied to a stored deal.
- **Honest confidence.** No invented percentages. Thin history returns
  `INSUFFICIENT_DATA` with the message *"Insufficient historical evidence."*
- **Graceful degradation.** With Hindsight or the LLM unreachable, the API still
  serves PostgreSQL-backed data, reports why memory is unavailable, and falls back
  to the deterministic evidence engine.
- **The model never touches the database.** The copilot only sees JSON produced by a
  small set of read-only backend tools.

---

## Quick start (Docker)

```bash
cp .env.example .env         # set JWT_SECRET at minimum
docker compose up --build
```

Then open http://localhost:8080 (web) and http://localhost:8001/api/health (API).

Containers:

| Service    | Image                            | Host port |
| ---------- | -------------------------------- | --------- |
| `web`      | nginx serving the built SPA      | 8080      |
| `api`      | FastAPI + uvicorn                | 8001      |
| `postgres` | `postgres:16-alpine`             | 5433      |
| `hindsight`| `ghcr.io/vectorize-io/hindsight` | 8889      |

Ollama runs on the host and is reached through `host.docker.internal`, so pull the
model once first:

```bash
ollama pull llama3.2:3b
```

If Hindsight is not reachable the application still runs — memory features report
`available: false` with a reason, and recommendations come from the deterministic
engine.

---

## Quick start (local development)

```bash
# backend
cd backend
pip install -r requirements.txt          # or use a virtualenv
alembic upgrade head
python -m app.db.seed                    # demo organisation + data
uvicorn app.main:app --reload --port 8000

# frontend (second terminal)
cd frontend
npm install
npm run dev                              # http://localhost:5173, proxies /api
```

### Demo credentials

| Role         | Email                              | Password           |
| ------------ | ---------------------------------- | ------------------ |
| Admin        | `admin@northwind-analytics.com`    | `demo-password-123`|
| Sales manager| `manager@northwind-analytics.com`  | `demo-password-123`|
| Sales rep    | `rep@northwind-analytics.com`      | `demo-password-123`|

---

## Configuration

All settings are environment variables (see `.env.example` and
`backend/app/config.py`):

| Variable | Purpose |
| -------- | ------- |
| `DATABASE_URL` | SQLAlchemy URL, e.g. `postgresql+psycopg2://user:pass@host/db` |
| `JWT_SECRET` | Signing secret for access tokens — **must be set in production** |
| `CORS_ORIGINS` | Comma-separated allowed origins |
| `LLM_BASE_URL`, `LLM_MODEL` | OpenAI-compatible endpoint (Ollama by default) |
| `HINDSIGHT_URL`, `HINDSIGHT_ENABLED` | Memory layer endpoint and kill switch |
| `SEED_DEMO_DATA`, `SEED_DEMO_PASSWORD` | Demo organisation bootstrap |

---

## API surface

Base path `/api`.

- `POST /auth/login`, `GET /auth/me`, `GET /auth/users`
- `GET|POST /deals`, `GET|PATCH|DELETE /deals/{id}`, `POST /deals/{id}/outcome`
- `POST /deals/{id}/analyze` — recommendation for one opportunity
- `GET  /deals/{id}/similar` — structured + memory-backed analogues
- `GET  /deals/{id}/memory`, `GET /deals/{id}/timeline`
- `POST /deals/{id}/copilot` — question answering over read-only tools
- `GET  /recommendations`, `POST /recommendations/{id}/feedback`
- `GET  /memory/status|references|search|timeline|insights`
- `GET  /dashboard`, `GET /analytics/win-loss`, `GET /analytics/health`
- `GET  /search`, `GET /health`, `GET /ready`

Interactive docs are enabled with `DEBUG=true` at `/api/docs`.

---

## Tests

```bash
cd backend
pytest
```

The suite runs against a throwaway `deal_intelligence_test` database with
Hindsight and the LLM deliberately disabled, so it verifies the **degradation
paths** as well as the happy path: organisation isolation, permission checks,
evidence citation, insufficient-history handling, and deterministic copilot
answers.

---

## Project layout

```
backend/
  app/api/           HTTP routers
  app/services/      recommendation, copilot, similarity, win/loss, memory, LLM
  app/models/        SQLAlchemy models (PostgreSQL)
  app/repositories/  query layer
  alembic/           migrations
  tests/             pytest suite
frontend/
  src/pages/         Dashboard, Pipeline, Deal detail, Analytics, Memory explorer…
  src/components/    shared UI primitives
docker-compose.yml   api + postgres + hindsight + web
```
