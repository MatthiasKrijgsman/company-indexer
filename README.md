# company-indexer

Data warehouse and API for Dutch company data. See [`VISION.md`](VISION.md) for the
product vision, architecture, current state, full API reference, and roadmap.

Backed by Postgres: a read API plus an inline enrichment chain (website search →
resolve website → scrape homepage → resolve careers URL → scrape jobs, plus
geocoding). Redis is running in infra but not yet used. No auth (local-only for now).

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
docker compose down -v && docker compose up -d
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
├── serper/         Serper.dev search client
├── llm/            Anthropic-backed website resolver
├── pdok/           PDOK Locatieserver geocoding client
├── scraper/        Tier-1 httpx website scraper
├── jobs/           Careers-URL resolver + job extractor
├── config.py       Settings loaded from .env
└── db.py           Async engine + session factory
```

See [`VISION.md`](VISION.md) for the full API reference and the design of each
enrichment package.
