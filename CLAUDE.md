# CLAUDE.md

Orientation for Claude Code sessions on this repo.

## What this is

A data warehouse + HTTP API for Dutch company data (KVK). Long-term, it will
ingest from the KVK API, enrich companies on-demand via a worker (geocoding,
Serper search, website fetching, LLM extraction), and serve a paid API. Right
now only a small slice is built.

## Plan documents

Three plan files in the repo root, read from most-specific to least:

- `mvp-plan.md` — the slice currently being implemented. Treat this as the
  source of truth for "what's in / what's out right now."
- `initial-plan.md` — fuller architecture, including everything deferred from
  the MVP (worker, enrichment, scraper).
- `initial-description.md` — the original one-pager describing the product.

If a task conflicts with `mvp-plan.md`, raise it — the plan is deliberate.

## Current scope (MVP — what's actually built)

- Postgres + Redis via `docker-compose.yml` (local only).
- SQLAlchemy 2 async models: `Company`, `CompanyName` + `NameType` enum,
  `Address`. All in `src/company_indexer/models/company.py`.
- Schema comes from `Base.metadata.create_all` (no Alembic yet — drop the
  volume and re-seed when models change).
- `scripts/seed_companies.py` — idempotent manual seed.
- FastAPI app with two read endpoints: `GET /companies` (supports
  `limit`/`offset`/`q`) and `GET /companies/{kvk_number}`.
- No auth. No worker. No enrichment. No KVK ingestion.

Redis is in compose so slice 2 doesn't touch infra, but no MVP code connects
to it yet.

## Stack

- Python 3.12+ (user runs 3.13 locally)
- FastAPI + uvicorn
- SQLAlchemy 2 (async) + asyncpg + greenlet
- Pydantic v2 + pydantic-settings
- redis-py (reserved, unused)
- ruff for lint (see `pyproject.toml`)

## Layout

```
src/company_indexer/
├── api/            FastAPI app, routes, deps
├── models/         SQLAlchemy models
├── schemas/        Pydantic response models
├── scripts/        Manual scripts (seed, etc.)
├── config.py       pydantic-settings reading .env
└── db.py           Async engine, session factory, Base, create_all
```

`src/` layout — the package is installed editable via `pip install -e ".[dev]"`.

## Run commands

```bash
docker compose up -d
python -m company_indexer.scripts.seed_companies
uvicorn company_indexer.api.app:app --reload
```

Reset DB when models change: `docker compose down -v && docker compose up -d`
then re-seed.

## Local env quirks

- Host ports: Postgres on `5434`, Redis on `6380` (user has another Postgres
  on 5432). Compose maps `5434:5432` and `6380:6379`.
- Postgres password is `mysecretpassword` (in `.env.example` and compose).
- Postgres 18 image — mount is `/var/lib/postgresql` (not
  `/var/lib/postgresql/data`, which is the v17-and-earlier convention).

## Conventions

- Async everywhere on the DB side — use `AsyncSession`, `selectinload` for
  relationships to avoid N+1.
- Response models in `schemas/` are separate from ORM models in `models/`.
  Use `ConfigDict(from_attributes=True)` + `CompanyRead.model_validate(obj)`.
- Indexes that need expressions (functional, partial) are defined as
  standalone `Index(...)` calls after the model class, not inside
  `__table_args__`.
- The `NameType` Postgres enum is declared once as `name_type_enum` and
  reused — don't let SQLAlchemy auto-generate a new type per column.
- Keep code boring and readable; this will be worked on by humans.

## What NOT to add yet

Per `mvp-plan.md`, the following are explicitly deferred — don't introduce
them unless the user asks:

- Alembic / migrations
- RQ, worker process, `enrichment/` package, `POST .../enrich`
- KVK scraper
- API tokens, call logging, billing
- Dockerfile for the app itself
- A big test suite (smoke tests are fine)
