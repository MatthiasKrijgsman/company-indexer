# Initial Setup Plan — company-indexer

A proposed starting layout for the Dutch company data warehouse + API described in `initial-description.md`. The goal is to stand up the skeleton: folders, config, infra, and the minimal code paths that glue API ⇄ queue ⇄ worker together. Actual scraping, enrichment, and auth logic are stubbed so they can be filled in incrementally.

## Stack choices

- **Python 3.12** (already have a `.venv`).
- **FastAPI** for the HTTP API — async-friendly, good OpenAPI, pairs well with Pydantic for the request/response schemas.
- **SQLAlchemy 2.x + Alembic** for ORM and migrations against PostgreSQL. Async engine (`asyncpg`) so it composes with FastAPI.
- **RQ** (Redis Queue) for the worker queue. Simple, fits the "one worker pulls jobs" model described. Alternative: Celery or Arq — RQ is the lightest fit for the current scope.
- **Redis** both as the RQ broker and a general cache if needed later.
- **httpx** for outbound HTTP (Serper, KVK, plain scraping) — async, works in both API and worker contexts.
- **Playwright** only loaded inside the worker (heavy dep). Keep it optional per-enrichment-method so the API container doesn't need browsers.
- **uv** or **pip-tools** for dependency management. Suggest `uv` given `pyproject.toml` is the modern default, but `requirements.txt` is fine too.
- **structlog** for structured logs.
- **pytest** + **pytest-asyncio** for tests.

## Proposed folder structure

```
company-indexer/
├── docker-compose.yml              # postgres + redis (+ optional api/worker services later)
├── pyproject.toml                  # deps, ruff/black config, pytest config
├── .env.example                    # documented env vars (no secrets committed)
├── .gitignore                      # extend current one with .env, __pycache__, etc.
├── alembic.ini
├── migrations/                     # alembic migrations
│   └── versions/
├── src/
│   └── company_indexer/
│       ├── __init__.py
│       ├── config.py               # pydantic-settings, reads .env
│       ├── db.py                   # async engine, session factory
│       ├── redis.py                # redis + RQ queue singletons
│       ├── logging.py              # structlog setup
│       │
│       ├── models/                 # SQLAlchemy models
│       │   ├── __init__.py
│       │   ├── company.py          # Company, CompanyName, NameType (enum), Address
│       │   └── enrichment.py       # EnrichmentJob, EnrichmentResult
│       │
│       ├── schemas/                # pydantic request/response models
│       │   ├── company.py
│       │   └── enrichment.py
│       │
│       ├── api/
│       │   ├── __init__.py
│       │   ├── app.py              # FastAPI app factory, middleware, routers
│       │   ├── deps.py             # db session dep
│       │   └── routes/
│       │       ├── companies.py    # GET /companies, GET /companies/{kvk}
│       │       └── enrichment.py   # POST /companies/{kvk}/enrich
│       │
│       ├── worker/
│       │   ├── __init__.py
│       │   ├── main.py             # RQ worker entrypoint
│       │   └── jobs.py             # dispatch -> enrichment methods
│       │
│       ├── enrichment/             # one module per method, same interface
│       │   ├── __init__.py
│       │   ├── base.py             # Enricher protocol: run(company) -> result
│       │   ├── geocode.py          # address -> GPS (stub; pick provider later)
│       │   ├── serper_search.py    # kvk -> candidate URLs
│       │   ├── fetch_website.py    # requests first, playwright fallback
│       │   └── llm_extract.py      # html -> structured fields
│       │
│       ├── scraper/                # KVK ingestion — stub for now
│       │   ├── __init__.py
│       │   └── kvk.py              # placeholder; manual seed via script
│       │
│       └── scripts/
│           └── seed_companies.py   # manual-insert helper you'll use initially
│
├── tests/
│   ├── conftest.py                 # db/redis fixtures (testcontainers or docker-compose)
│   ├── test_api_companies.py
│   └── test_enrichment_dispatch.py
│
├── initial-description.md
├── initial-plan.md                 # this file
└── README.md                       # how to run locally
```

## Infrastructure — `docker-compose.yml`

Two services for now, per the description:

- `postgres:16` — exposed on `5432`, volume-mounted for persistence, env-configured DB/user/password.
- `redis:7` — exposed on `6379`, AOF persistence on.

The API and worker run on the host against these during early development (faster iteration than rebuilding containers). Add `api` and `worker` services to the compose file once the code stabilizes.

## Data model sketch

- **Company** — `id`, `kvk_number` (unique, the external identifier — used in URLs and lookups), timestamps. No `name` column on `Company` itself; names live in `CompanyName`.
- **CompanyName** — `id`, `company_id`, `name`, `type` (enum, see below), timestamps. A company has one or more rows here. Consider a partial unique index on `(company_id, type)` for types that should only appear once (e.g. `statutory`), and a plain index on `name` for search.
- **NameType** — Postgres enum. Starter values based on what KVK exposes:
  - `statutory` — statutaire naam (legal entity name)
  - `trade` — handelsnaam (trade name / DBA)
  - `short` — verkorte naam (short form)
  - `alias` — anything else we discover via enrichment (e.g. a brand name scraped from a website)
  Define it as a native Postgres enum via SQLAlchemy so migrations are explicit when we add new values.
- **Address** — `id`, `company_id`, raw fields (street, postcode, city), `lat`/`lon` (nullable; filled by geocode enrichment).
- **EnrichmentJob** — `id`, `company_id`, `method`, `status` (`queued`/`running`/`done`/`failed`), `error`, timestamps, `rq_job_id`.
- **EnrichmentResult** — polymorphic result bag keyed by `method`; stores the output (URLs found, HTML path, LLM-extracted JSON). Could start as one table with a JSONB `data` column.

Lookups and URL params use `kvk_number`, not the surrogate `id`. `GET /companies/{kvk}` returns the company with its full list of names (each tagged with its type) and addresses.

Auth and API-call logging are deliberately out of scope for the initial local/test setup — to be added later when this moves toward a paid API.

HTML snapshots from `fetch_website` get stored on disk (e.g. `./data/html/{company_id}/{timestamp}.html`) with a DB row pointing to the path. Keeps the DB lean.

## Key flows

1. **Seed** — run `scripts/seed_companies.py` to insert a handful of companies with KVK numbers and addresses.
2. **Enrich request** — `POST /companies/{kvk}/enrich` with a body like `{"methods": ["geocode", "serper_search"]}`. Handler:
   - creates an `EnrichmentJob` row per method
   - enqueues an RQ job referencing the job id
   - returns `202` with the job ids
3. **Worker** — `worker/main.py` runs `rq worker`. `jobs.py` loads the `EnrichmentJob`, picks the right `Enricher` from a registry, runs it, writes an `EnrichmentResult`, updates job status.
4. **Query** — `GET /companies/{kvk}` returns company + addresses + latest enrichment results.

## Environment variables (`.env.example`)

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/company_indexer
REDIS_URL=redis://localhost:6379/0
SERPER_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
KVK_API_KEY=
LOG_LEVEL=INFO
HTML_STORAGE_DIR=./data/html
```

## Suggested order of implementation

1. `pyproject.toml`, `.env.example`, `docker-compose.yml`, `.gitignore` updates, basic `README.md` with run instructions.
2. `config.py`, `db.py`, `redis.py`, `logging.py` — the plumbing.
3. Models + first Alembic migration.
4. `seed_companies.py` so there's data to query.
5. FastAPI skeleton: `GET /companies/{kvk}`.
6. Enrichment scaffolding: `base.Enricher`, registry, `POST .../enrich` endpoint, RQ enqueue, worker entrypoint. Start with a trivial no-op enricher end-to-end.
7. Fill in real enrichers one at a time: `geocode` → `serper_search` → `fetch_website` → `llm_extract`.
8. KVK scraper (left for later per the description).
9. Later, once the core works: API tokens, per-call logging, and anything else needed to turn this into a paid API.

## Open questions to decide before/while coding

- **Geocoding provider** — PDOK (free, Dutch-specific, fits the domain) vs Google vs Mapbox. PDOK is probably the right default.
- **LLM provider** — OpenAI vs Anthropic. Either fits; pick one to start and put it behind `enrichment/llm_extract.py` so swapping is local.
- **EnrichmentResult shape** — one table with JSONB, or one table per method? JSONB is faster to start; split later if queries get ugly.
- **Playwright in the worker** — ship it in a dedicated worker image with browsers baked in, or make it optional and route `fetch_website` jobs to a separate queue. Matters once you containerize the worker.
