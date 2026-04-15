# company-indexer

Data warehouse and API for Dutch company data. See `initial-description.md` for the
long-term vision and `mvp-plan.md` for the scope of the current slice.

The MVP exposes two read-only endpoints backed by Postgres. Redis is running in
infra but not yet used. No auth (local-only for now).

## Prerequisites

- Python 3.12+
- Docker (for Postgres + Redis)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Run

```bash
# 1. Start infra
docker compose up -d

# 2. Seed a few companies (idempotent, safe to re-run)
python -m company_indexer.scripts.seed_companies

# 3. Run the API
uvicorn company_indexer.api.app:app --reload
```

Then:

- <http://localhost:8000/docs> — interactive API docs
- `curl http://localhost:8000/companies`
- `curl http://localhost:8000/companies/33014286`
- `curl 'http://localhost:8000/companies?q=philips'`

## Reset the database

Schema currently comes from `Base.metadata.create_all` — so whenever models
change, wipe the volume and start over:

```bash
docker compose down -v
docker compose up -d
python -m company_indexer.scripts.seed_companies
```

Alembic will be introduced once the schema stabilizes.

## Project layout

```
src/company_indexer/
├── api/            FastAPI app, routes, dependencies
├── models/         SQLAlchemy models
├── schemas/        Pydantic response models
├── scripts/        Manual scripts (seed, etc.)
├── config.py       Settings loaded from .env
└── db.py           Async engine + session factory
```
