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
- SQLAlchemy 2 async models:
  - `Company`, `CompanyName` + `NameType` enum, `Address` (with nullable
    `lat`/`lon`/`geocoded_at`) — in `models/company.py`.
  - `WebsiteSearch` + `WebsiteSearchStatus` enum — in
    `models/website_search.py`. Stores each Serper attempt (raw JSON).
  - `CompanyWebsite` + `WebsiteConfidence` enum — in
    `models/company_website.py`. Stores each LLM resolution (history, not
    overwrite).
- Schema comes from `Base.metadata.create_all` (no Alembic yet — drop the
  volume and re-seed when models change).
- `scripts/seed_companies.py` — idempotent manual seed.
- FastAPI app. Read endpoints: `GET /companies` (supports
  `limit`/`offset`/`q`) and `GET /companies/{kvk_number}`.
- Enrichment endpoints (sync, inline — no worker yet):
  - `POST/GET /companies/{kvk}/website-search` — Serper search for the KVK
    number with aggregator domains excluded; raw result persisted.
  - `POST /companies/{kvk}/resolve-website` + `GET .../website` — Claude
    Haiku 4.5 picks the likely homepage from stored Serper candidates;
    always inserts a new `CompanyWebsite` row.
  - `POST /companies/{kvk}/geocode` — PDOK Locatieserver populates every
    address's `lat`/`lon`/`geocoded_at` (address-level matches only).
- No auth. No worker. No KVK ingestion.

Redis is in compose so slice 2 doesn't touch infra, but no MVP code connects
to it yet.

## Stack

- Python 3.12+ (user runs 3.13 locally)
- FastAPI + uvicorn
- SQLAlchemy 2 (async) + asyncpg + greenlet
- Pydantic v2 + pydantic-settings
- httpx (outbound calls to Serper + PDOK)
- anthropic (async Claude SDK) — Haiku 4.5 is the default for structured
  extraction
- redis-py (reserved, unused)
- ruff for lint (see `pyproject.toml`)

## Layout

```
src/company_indexer/
├── api/            FastAPI app, routes, deps
├── models/         SQLAlchemy models
├── schemas/        Pydantic response models
├── scripts/        Manual scripts (seed, etc.)
├── serper/         Serper.dev client + excluded-domains helper
├── llm/            Anthropic-backed website resolver
├── pdok/           PDOK Locatieserver geocoding client
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
- Enrichment needs `SERPER_API_KEY` and `ANTHROPIC_API_KEY` in `.env`
  (see `.env.example`). PDOK (geocoding) is keyless.

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
  Same pattern for `website_search_status_enum` and
  `website_confidence_enum`.
- External API clients live in their own top-level package (`serper/`,
  `pdok/`, `llm/`). Each exposes an async call returning a typed
  dataclass with `ok: bool` + `error: str | None` + the payload. Never
  raise on HTTP errors — the caller inspects `ok` and maps it to an HTTP
  status. Error codes are short strings (`timeout`, `no_credits`,
  `no_match`, `http_{n}`) that are safe to persist and match on.
- LLM calls use `anthropic.AsyncAnthropic` + `messages.parse()` with a
  Pydantic output model. Put a frozen, verbatim system prompt in
  `system=[{..., "cache_control": {"type": "ephemeral"}}]` — the marker
  is free even when prompts are under the minimum cacheable prefix.
- For probabilistic outputs (LLM website picks, PDOK matches), prefer
  returning null + a `none`/`low`-confidence marker over guessing.
  A wrong answer is worse than no answer.
- Enrichment endpoints are sync inline in the request path for now. When
  moved to a worker (future slice), the provider clients in `serper/` /
  `llm/` / `pdok/` should port over untouched.
- Keep code boring and readable; this will be worked on by humans.
- When adding new endpoints to the API, document them in `docs.md`.

## What NOT to add yet

Per `mvp-plan.md`, the following are explicitly deferred — don't introduce
them unless the user asks:

- Alembic / migrations
- RQ / worker process — enrichment lives inline in request handlers for
  now. A unified `enrichment/` package or generic `POST .../enrich`
  endpoint is also not built yet; current endpoints are per-action
  (`/website-search`, `/resolve-website`, `/geocode`).
- KVK scraper / ingestion
- API tokens, call logging, billing
- Dockerfile for the app itself
- A big test suite (smoke tests are fine)
