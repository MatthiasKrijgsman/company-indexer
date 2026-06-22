# CLAUDE.md

Orientation for Claude Code sessions on this repo.

## What this is

A data warehouse + HTTP API for Dutch company data (KVK). Long-term, it will
ingest from the KVK API, enrich companies on-demand via a worker (geocoding,
Serper search, website fetching, LLM extraction), and serve a paid API. Right
now the read API plus a full inline enrichment chain is built; worker, KVK
ingestion, and billing are not.

## Project docs

- `VISION.md` — the single source of truth: product vision, architecture,
  what's built today, the data model, the full API reference, and the roadmap
  of future slices. Read this first; if a task conflicts with its "What's
  built" or "Conventions" sections, raise it.
- `README.md` — local run book.
- This file — short orientation for coding sessions.

(The old split plan/doc files — `initial-description.md`, `initial-plan.md`,
`mvp-plan.md`, `plan-scrape.md`, `plan-jobs.md`, `docs.md` — were consolidated
into `VISION.md`.)

## Current scope (what's actually built)

The enrichment chain runs **sync inline** (no worker): search → resolve website
→ scrape homepage → resolve careers URL → scrape jobs, plus geocoding as an
independent branch.

- Postgres + Redis via `docker-compose.yml` (local only).
- SQLAlchemy 2 async models:
  - `Company`, `CompanyName` + `NameType` enum, `Address` (with nullable
    `lat`/`lon`/`geocoded_at`) — in `models/company.py`.
  - `WebsiteSearch` + `WebsiteSearchStatus` enum — `models/website_search.py`.
    Stores each Serper attempt (raw JSON).
  - `CompanyWebsite` + `WebsiteConfidence` enum — `models/company_website.py`.
    Stores each LLM website resolution (history, not overwrite).
  - `WebsiteScrape` / `WebsitePage` (+ status & fetch-method enums) —
    `models/website_scrape.py`. One scrape + its page rows; markdown in
    Postgres, raw HTML on disk.
  - `CompanyCareersUrl`, `JobsScrape`, `Job` (+ enums) — `models/jobs.py`.
    Careers-URL resolution and extracted job postings.
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
  - `POST /companies/{kvk}/scrape` + `GET .../scrape` + `GET .../scrapes` —
    Tier-1 httpx homepage scrape (real-browser headers, JS/block detection),
    HTML to disk + markdown to Postgres.
  - `POST /companies/{kvk}/resolve-careers` + `GET .../careers-url` — Haiku
    picks the careers page from homepage links: the company's own pages plus
    qualifying external werkenbij/ATS links (admitted on list-free signals),
    with a one-level follow of an on-domain careers landing page to its
    external destination.
  - `POST /companies/{kvk}/scrape-jobs` + `GET .../jobs` +
    `GET .../jobs-history` — fetch careers page, Haiku extracts open positions.
  - `POST /companies/{kvk}/geocode` — PDOK Locatieserver populates every
    address's `lat`/`lon`/`geocoded_at` (address-level matches only).
- No auth. No worker. No KVK ingestion.

Redis is in compose so the future worker slice doesn't touch infra, but no
code connects to it yet.

## Stack

- Python 3.12+ (user runs 3.13 locally)
- FastAPI + uvicorn
- SQLAlchemy 2 (async) + asyncpg + greenlet
- Pydantic v2 + pydantic-settings
- httpx[http2] (outbound calls to Serper, PDOK, website scraping)
- anthropic (async Claude SDK) — Haiku 4.5 is the default for structured
  extraction
- trafilatura (HTML → markdown), beautifulsoup4 (link parsing)
- redis-py (reserved, unused)
- ruff for lint (see `pyproject.toml`)

## Layout

```
src/company_indexer/
├── api/            FastAPI app, routes, deps
│   └── routes/     companies, website_searches, geocoding, scrapes, jobs
├── models/         SQLAlchemy models
├── schemas/        Pydantic response models
├── scripts/        Manual scripts (seed, etc.)
├── serper/         Serper.dev client + excluded-domains helper
├── llm/            Anthropic-backed website resolver
├── pdok/           PDOK Locatieserver geocoding client
├── scraper/        Tier-1 httpx scraper (headers, fetch, detect, extract,
│                   discover, storage, orchestrator)
├── jobs/           Careers-URL resolver + job extractor (candidates,
│                   resolver, extractor, orchestrator)
├── pricing/        EUR cost accounting for Serper + Haiku (rates, usage,
│                   estimates) — backs the frontend cost indicator
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

## Frontend (dev only)

`frontend/` is a **development-only** web console for driving the API by hand
(browse companies + run the enrichment chain from the browser). Not part of the
product — no auth, no deploy, no tests.

- Stack: React 19 + Vite + Tailwind v4 + `@tanstack/react-query` +
  `@matthiaskrijgsman/mat-ui` (the user's own component library).
- Run: `cd frontend && npm install && npm run dev` (needs the API on :8000).
  The Vite dev server proxies `/companies` → `localhost:8000`, so the backend
  needs **no CORS** config. Don't add CORS middleware for the frontend's sake.
- **`frontend/src/api/types.ts` is hand-maintained** — it mirrors the Pydantic
  schemas in `schemas/`. There is no codegen, so when you change an API
  response schema, update `types.ts` to match (it has a header comment saying
  so). The react-query hooks live in `frontend/src/api/hooks.ts`; one
  enrichment section component per step in `frontend/src/pages/sections.tsx`.
- See `frontend/README.md` for details.

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
  Same pattern for the other native enums (`website_search_status_enum`,
  `website_confidence_enum`, `website_scrape_status_enum`,
  `website_page_*_enum`, `jobs_scrape_status_enum`,
  `job_employment_type_enum`).
- Enrichment steps are **append-only**: each attempt inserts a new row
  (never overwrite); queries are "latest by `created_at`". A failed or
  null attempt is still persisted — the status enums are the log, there's
  no separate log table.
- External clients + the internal enrichment packages (`serper/`, `pdok/`,
  `llm/`, `scraper/`, `jobs/`) each expose async calls returning a typed
  dataclass with `ok: bool` + `error: str | None` + the payload. Never
  raise on HTTP errors — the caller inspects `ok` and maps it to an HTTP
  status. Error codes are short strings (`timeout`, `no_credits`,
  `no_match`, `http_{n}`) that are safe to persist and match on.
- Raw HTML lives on the filesystem under `SCRAPED_HTML_DIR` (default
  `data/scraped_html/`); only `storage.py` touches the filesystem. The DB
  stores a path **relative to the root** (`html_path`). Extracted markdown
  lives in Postgres. `html_path` is internal — never exposed on a `*Read`
  schema.
- Enrichment that needs an LLM uses the two-cheap-calls pattern (locate
  then extract), each a separate Haiku call — not one expensive agent.
- LLM calls use `anthropic.AsyncAnthropic` + `messages.parse()` with a
  Pydantic output model. Put a frozen, verbatim system prompt in
  `system=[{..., "cache_control": {"type": "ephemeral"}}]` — the marker
  is free even when prompts are under the minimum cacheable prefix.
- For probabilistic outputs (LLM website picks, PDOK matches), prefer
  returning null + a `none`/`low`-confidence marker over guessing.
  A wrong answer is worse than no answer.
- Enrichment endpoints are sync inline in the request path for now. When
  moved to a worker (future slice), the provider packages (`serper/`,
  `llm/`, `pdok/`, `scraper/`, `jobs/`) should port over untouched.
- Keep code boring and readable; this will be worked on by humans.
- When adding new endpoints to the API, document them in the API reference
  section of `VISION.md`.

## What NOT to add yet

Per `VISION.md`, the following are explicitly deferred — don't introduce
them unless the user asks:

- Alembic / migrations
- RQ / worker process — enrichment lives inline in request handlers for
  now. A unified `enrichment/` package or generic `POST .../enrich`
  dispatcher is also not built yet; current endpoints are per-action
  (`/website-search`, `/resolve-website`, `/scrape`, `/resolve-careers`,
  `/scrape-jobs`, `/geocode`).
- KVK API scraper / ingestion (manual seed only for now)
- Website-scrape Tier 2 (Jina/Firecrawl/Playwright) and subpage discovery —
  current scraper is Tier-1 httpx, homepage only.
- Jobs: external werkenbij/ATS careers links are now considered at *resolve*
  time (`jobs/candidates.py`), but ATS vendor tagging, iframe follow, and a
  self-learning ATS list are deferred (see VISION roadmap).
- API tokens, call logging, billing
- Dockerfile for the app itself
- A big test suite (smoke tests are fine)

See the Roadmap section of `VISION.md` for the planned shape of each.
