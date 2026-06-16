# company-indexer — Vision, Plan & API Reference

The single source of truth for this project: the product vision, the target
architecture, what is actually built today, the roadmap of future slices, and
the full HTTP API reference.

This file supersedes the old split docs (`initial-description.md`,
`initial-plan.md`, `mvp-plan.md`, `plan-scrape.md`, `plan-jobs.md`, `docs.md`).
`CLAUDE.md` is the short orientation for coding sessions; `README.md` is the
run book. Everything else lives here.

> If a task conflicts with the **What's built** or **Conventions** sections,
> raise it — the current shape is deliberate.

---

## 1. Product vision

A **data warehouse + HTTP API for Dutch company data (KVK)**.

Basic records — names, KVK numbers, and Dutch addresses — are ingested from the
KVK search API (manual seed for now; scraper deferred). On request, a company
can be **enriched** on demand through a series of independent methods:

- Geocode each address to GPS coordinates.
- Use Serper (Google) to locate the company's own website by KVK number.
- Pick the real homepage from the search results with an LLM.
- Fetch the website and store its content (HTML on disk, markdown in Postgres).
- Extract structured data from that content with an LLM — currently open job
  positions; later contacts, summaries, branding.

The data is queried over an HTTP API. Long-term this becomes a **paid API**:
API tokens, per-call logging, and billing. Infrastructure is Postgres + a Redis
queue, run locally via `docker-compose` for now.

The guiding shape: a thin API in front of a warehouse, with enrichment as a set
of small, independent, individually-debuggable steps that each persist their
attempt (success *or* failure) as a first-class row.

---

## 2. Architecture & stack

### Stack

- **Python 3.12+** (user runs 3.13 locally).
- **FastAPI + uvicorn** — async HTTP API, OpenAPI docs.
- **SQLAlchemy 2 (async)** + **asyncpg** + **greenlet** — ORM against Postgres.
- **Pydantic v2 + pydantic-settings** — response schemas + env config.
- **httpx[http2]** — all outbound HTTP (Serper, PDOK, website scraping).
- **anthropic** (async Claude SDK) — Claude **Haiku 4.5** for structured
  extraction via `messages.parse()`.
- **trafilatura** — HTML → clean markdown extraction.
- **beautifulsoup4** — HTML link parsing for careers-page candidates.
- **redis-py** — reserved for the future worker queue; **not used yet**.
- **ruff** — lint (config in `pyproject.toml`).

### Infrastructure

- `docker-compose.yml` runs **Postgres 18** and **Redis 7**, bound to
  localhost only. The API runs on the host via `uvicorn` for fast iteration.
- Schema is created from the models via `Base.metadata.create_all` on app
  startup and at the top of the seed script. **No Alembic yet** — when models
  change, drop the volume and re-seed.
- Redis is in compose from day one so the future worker slice doesn't have to
  touch infra; no code connects to it today.

### Package layout

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
├── pricing/        EUR cost accounting (Serper + Haiku rates, token usage,
│                   per-action estimates) — backs GET /pricing + cost columns
├── config.py       pydantic-settings reading .env
└── db.py           Async engine, session factory, Base, create_all
```

`src/` layout — the package is installed editable via `pip install -e ".[dev]"`.

### The enrichment-provider pattern

Each external integration (`serper/`, `pdok/`, `llm/`, plus the internal
`scraper/` and `jobs/` packages) follows one convention:

- Small, focused modules exposing async functions.
- Each returns a **typed dataclass** with `ok: bool` + `error: str | None` +
  the payload. **Never raise on HTTP/provider errors** — the caller inspects
  `ok` and maps it to an HTTP status.
- Error codes are short strings (`timeout`, `no_credits`, `no_match`,
  `http_{n}`) that are safe to persist and match on.
- For probabilistic outputs (LLM picks, PDOK matches), prefer returning
  `null` + a `none`/`low`-confidence marker over guessing. **A wrong answer is
  worse than no answer.**
- Enrichment runs **sync inline in the request handler** today. The provider
  packages are written so the same code ports into a worker later with no
  changes.

### Append-only history

Enrichment steps **never overwrite**. Each attempt inserts a new row; queries
are always "latest by `created_at`". This holds for `WebsiteSearch`,
`CompanyWebsite`, `WebsiteScrape`/`WebsitePage`, `CompanyCareersUrl`,
`JobsScrape`/`Job`. A failed or null attempt is still persisted — the status
enums *are* the log; there is no separate log table.

---

## 3. What's built today

The current slice covers the read API plus a full enrichment chain run inline:

**search → resolve website → scrape homepage → resolve careers URL →
scrape jobs**, with geocoding as an independent branch.

### Data ingest

- `scripts/seed_companies.py` — idempotent manual seed (`INSERT ... ON CONFLICT
  DO NOTHING` on `kvk_number`). No KVK API scraper yet.

### Read API

- `GET /companies` (supports `limit`/`offset`/`q`) and
  `GET /companies/{kvk_number}` — names + addresses eager-loaded.

### Enrichment (sync inline, no worker)

1. **Website search** — `POST/GET /companies/{kvk}/website-search`. Serper
   Google search for the KVK number, business-registry aggregators excluded,
   raw JSON persisted.
2. **Resolve website** — `POST /companies/{kvk}/resolve-website` +
   `GET .../website`. Claude Haiku 4.5 picks the likely homepage from the
   stored Serper candidates (metadata only — it does not fetch pages). Inserts
   a new `CompanyWebsite` row; `url=null` is a valid outcome.
3. **Scrape homepage** — `POST /companies/{kvk}/scrape` + `GET .../scrape` +
   `GET .../scrapes`. Tier-1 httpx fetch with a real-browser header profile,
   JS/block detection, raw HTML to disk under `SCRAPED_HTML_DIR`, markdown +
   title to Postgres. **Homepage only** (subpage discovery deferred).
4. **Resolve careers URL** — `POST /companies/{kvk}/resolve-careers` +
   `GET .../careers-url`. Deterministic same-domain candidate building from the
   homepage HTML (keyword-scored `<a>` links + fallback paths), then a Haiku
   pick. Inserts a `CompanyCareersUrl` row; null is valid.
5. **Scrape jobs** — `POST /companies/{kvk}/scrape-jobs` + `GET .../jobs` +
   `GET .../jobs-history`. Fetches the careers page, extracts markdown, runs
   Haiku to enumerate open positions. Inserts a `JobsScrape` + one `Job` per
   position; an empty-but-clean page yields `status="no_jobs"`.
6. **Geocode** — `POST /companies/{kvk}/geocode`. PDOK Locatieserver populates
   each address's `lat`/`lon`/`geocoded_at` (street-address-level matches only,
   keyless).

No auth, no worker, no KVK ingestion, no billing.

A **development-only** web console for exercising these endpoints by hand lives
in `frontend/` (React + Vite + Tailwind + react-query + `@matthiaskrijgsman/mat-ui`).
It is not part of the product — see `frontend/README.md`.

---

## 4. Data model

Surrogate `id` PKs everywhere; lookups and URL params use `kvk_number`, never
the surrogate. Native Postgres enums are declared **once** and reused across
columns (don't let SQLAlchemy auto-generate a type per column). Expression
indexes (functional, partial) are standalone `Index(...)` calls after the model
class, not in `__table_args__`.

### Core (`models/company.py`)

- **Company** — `id`, `kvk_number` (unique, indexed), `created_at`,
  `updated_at`. No name column; names live in `CompanyName`.
- **CompanyName** — `id`, `company_id` (FK cascade), `name`, `type`
  (`NameType`), `created_at`. Index on `company_id`; partial unique index on
  `(company_id, type)` for `statutory` so there's one legal name per company.
- **NameType** enum (`name_type_enum`): `statutory` (statutaire naam), `trade`
  (handelsnaam), `short` (verkorte naam), `alias` (discovered via enrichment).
- **Address** — `id`, `company_id` (FK cascade), `street`, `house_number`,
  `postcode`, `city`, `country` (default `NL`), `lat`/`lon`/`geocoded_at`
  (nullable; populated by the geocode step).

### Website search & resolution

- **WebsiteSearch** (`models/website_search.py`) + `WebsiteSearchStatus` enum —
  one row per Serper attempt, raw JSON stored.
- **CompanyWebsite** (`models/company_website.py`) + `WebsiteConfidence` enum
  (`high`/`medium`/`low`/`none`) — one row per LLM resolution, with `url` and
  `homepage_url` (`scheme://netloc/` of `url`).

### Website scrape (`models/website_scrape.py`)

- **WebsiteScrape** + `WebsiteScrapeStatus` enum (`ok`, `partial`, `failed`,
  `skipped_no_website`, `skipped_js_heavy`, `skipped_dead_domain`) — one row per
  scrape attempt, with `pages_attempted`/`pages_ok`/`pages_failed` counters.
- **WebsitePage** + `WebsitePageFetchMethod` enum (`http`, `jina`, `firecrawl`,
  `playwright` — only `http` used today) + `WebsitePageStatus` enum (`ok`,
  `http_4xx`, `http_5xx`, `timeout`, `network_error`, `js_required`, `blocked`,
  `dead_domain`, `non_html`) — one row per URL × scrape. `markdown` in Postgres;
  raw HTML on disk via `html_path` (relative to `SCRAPED_HTML_DIR`).
  `UniqueConstraint(scrape_id, normalized_url)`; `Index(company_id, url,
  content_hash)` for future cross-scrape diffs.

### Jobs (`models/jobs.py`)

- **CompanyCareersUrl** — one row per careers-URL resolution. `source_scrape_id`
  FK to the `WebsiteScrape` whose homepage HTML was read; nullable `url`
  (null = no same-domain careers page); reuses `website_confidence` enum.
- **JobsScrape** + `JobsScrapeStatus` enum (`ok`, `no_jobs`, `no_careers_page`,
  `js_required`, `blocked`, `failed`, `llm_error`) — one row per extraction
  attempt, `source_careers_id` FK, `html_path` on disk.
- **Job** + `JobEmploymentType` enum (`full_time`, `part_time`, `contract`,
  `internship`, `unknown`) — one row per extracted position per scrape
  (append-only; cross-scrape diff is a later concern).

### Storage decision

Markdown lives in Postgres; **raw HTML lives on the filesystem** under a
configurable root (`SCRAPED_HTML_DIR`, default `data/scraped_html/`), laid out
as `{company_id}/{scrape_id}/{page_id}.html` for website pages and
`{company_id}/jobs/{jobs_scrape_id}.html` for careers pages. The DB stores a
path **relative to the root** so the root can move (different env, object
storage later) without a data migration. Keeping HTML out of Postgres avoids
row-size/backup bloat; keeping it on disk (vs. discarding) means a better
extractor can re-run cheaply without re-fetching. The root is gitignored.

---

## 5. API reference

HTTP API for Dutch company (KVK) data. No auth yet — local only.
Base URL: `http://localhost:8000`. Interactive docs at `/docs`.

> **Conventions:** Protocol-level preconditions return non-2xx (`404` unknown
> company, `400` missing upstream step, `502` provider failure). Content-level
> outcomes (blocked, js_required, no_jobs, null pick) return `200` with the
> status in the body — the attempt is still persisted.

### `GET /companies`

List companies with optional substring search on any associated name.

| Param    | Type   | Default | Description                                   |
|----------|--------|---------|-----------------------------------------------|
| `limit`  | int    | `50`    | Page size, `1`–`200`.                         |
| `offset` | int    | `0`     | Rows to skip.                                 |
| `q`      | string | —       | Case-insensitive substring match on any name. |

`200 OK`:

```json
{
  "items": [
    {
      "kvk_number": "12345678",
      "names": [{ "name": "Acme B.V.", "type": "statutory" }],
      "addresses": [
        {
          "street": "Damrak", "house_number": "1",
          "postcode": "1012LG", "city": "Amsterdam", "country": "NL",
          "lat": "52.3740", "lon": "4.8897", "geocoded_at": null
        }
      ]
    }
  ],
  "limit": 50,
  "offset": 0
}
```

### `GET /companies/{kvk_number}`

Fetch a single company by KVK number.

- `200 OK` — a single `CompanyRead` (same shape as `items[]` above).
- `404 Not Found` — no company with that KVK number.

### `POST /companies/{kvk_number}/website-search`

Runs a Google search (via Serper) for `kvk "{kvk_number}"` with business-registry
aggregators excluded, and stores the raw result. The attempt is persisted whether
it succeeds or fails.

- `200 OK` — `WebsiteSearchDetail` (raw Serper JSON under `results`).
- `404 Not Found` — unknown company.
- `502 Bad Gateway` — Serper call failed (timeout, network, no credits,
  unauthorized, non-200). The attempt row is still written with `status="failed"`.

### `GET /companies/{kvk_number}/website-search`

Every website-search attempt for the company, newest first, raw Serper JSON
inlined. Empty list if none run yet.

- `200 OK` — `WebsiteSearchDetail[]`.
- `404 Not Found` — unknown company.

### `POST /companies/{kvk_number}/resolve-website`

Reads the latest successful `WebsiteSearch` and asks Claude Haiku 4.5 to pick the
candidate most likely to be the company's own site (Serper metadata only — no page
fetch). Always inserts a new `CompanyWebsite` row. `url=null` is valid.

- `200 OK` — `WebsiteRead`.
- `400 Bad Request` — no successful website search on record. Call
  `POST .../website-search` first.
- `404 Not Found` — unknown company.
- `502 Bad Gateway` — LLM call failed. A row is still written with
  `confidence="none"`, `reason="resolver_error: ..."`.

### `GET /companies/{kvk_number}/website`

Most recent website resolution.

- `200 OK` — `WebsiteRead`.
- `404 Not Found` — unknown company, or no resolution run yet.

### `POST /companies/{kvk_number}/scrape`

Scrapes the homepage (latest `CompanyWebsite.homepage_url`). Classifies it,
persists raw HTML to disk under `SCRAPED_HTML_DIR`, stores extracted markdown +
metadata. Always inserts a new `WebsiteScrape` plus exactly one `WebsitePage`
child. Page-level outcomes (blocked, js_required, timeout) are recorded on
`WebsitePage.status` and still return `200`.

- `200 OK` — `WebsiteScrapeRead` with `pages`.
- `400 Bad Request` — no resolved `homepage_url`. Call `POST .../resolve-website`
  first.
- `404 Not Found` — unknown company.

### `GET /companies/{kvk_number}/scrape`

Most recent scrape, page list inlined.

- `200 OK` — `WebsiteScrapeRead`.
- `404 Not Found` — unknown company, or no scrape run yet.

### `GET /companies/{kvk_number}/scrapes`

Scrape history, newest first, each with its `pages` list.

- `200 OK` — `WebsiteScrapeRead[]` (empty array if never scraped).
- `404 Not Found` — unknown company.

### `POST /companies/{kvk_number}/resolve-careers`

Builds candidate careers-page URLs from the homepage HTML of the latest `OK`
`WebsiteScrape` (same-domain links keyword-scored against `vacature`, `werken`,
`jobs`, `career` + a small fallback path list), then asks Claude Haiku 4.5 to pick
the most likely careers page. Always inserts a new `CompanyCareersUrl` row. A null
`url` with `confidence="none"` is a valid, first-class outcome. External ATS
platforms (Recruitee, Homerun, …) are out of scope this slice — off-domain links
are dropped.

- `200 OK` — `CompanyCareersUrlRead`.
- `400 Bad Request` — no `OK` website scrape on record. Call `POST .../scrape`
  first.
- `404 Not Found` — unknown company.
- `502 Bad Gateway` — LLM call failed. A row is still written with
  `confidence="none"`, `reason="resolver_error: ..."`.

### `GET /companies/{kvk_number}/careers-url`

Latest careers-URL resolution, including the null outcome.

- `200 OK` — `CompanyCareersUrlRead`.
- `404 Not Found` — unknown company, or no resolution run yet.

### `POST /companies/{kvk_number}/scrape-jobs`

Fetches the latest resolved careers URL, extracts markdown, runs Claude Haiku 4.5
to enumerate open positions. Always inserts a new `JobsScrape` plus one `Job` per
position. Page-level outcomes (`blocked`, `js_required`, fetch failures) sit on
`JobsScrape.status` and still return `200`. An empty-but-clean page yields
`status="no_jobs"`; a null upstream careers URL is rejected with `400` (the null
was already persisted at resolve time).

- `200 OK` — `JobsScrapeRead` with `jobs`.
- `400 Bad Request` — no careers URL, or no `OK` upstream website scrape.
- `404 Not Found` — unknown company.

### `GET /companies/{kvk_number}/jobs`

Latest `JobsScrape` with jobs inlined.

- `200 OK` — `JobsScrapeRead`.
- `404 Not Found` — unknown company, or no jobs scrape run yet.

### `GET /companies/{kvk_number}/jobs-history`

Jobs-scrape history, newest first.

- `200 OK` — `JobsScrapeRead[]` (empty array if never scraped).
- `404 Not Found` — unknown company.

### `POST /companies/{kvk_number}/geocode`

Geocodes every address via PDOK Locatieserver (free, keyless, BAG-backed). Only
street-address-level matches (`type=adres`) are accepted. Each address's `lat`,
`lon`, `geocoded_at` are updated; unresolvable addresses keep their coordinates
but still get `geocoded_at` stamped.

- `200 OK` — updated `CompanyRead`.
- `404 Not Found` — unknown company.
- `502 Bad Gateway` — one or more PDOK calls failed at the network level. Partial
  successes are still committed.

### `GET /pricing`

Static rate card + per-action EUR cost estimates for the cost indicator.
Derived from the configured `USD_TO_EUR` rate (default `0.92`, no live FX) and
the provider rates in `pricing/pricing.py` (Serper ~$0.001/search; Claude Haiku
4.5 $1/$5 per MTok in/out).

- `200 OK` — `{ usd_to_eur, rates_usd, estimates_eur: { website_search,
  resolve_website, scrape, resolve_careers, scrape_jobs, geocode } }`.

**Cost accounting.** The two paid steps record their actual EUR cost on the
persisted row: `WebsiteSearch.cost_eur` (Serper flat, set only on success) and
`CompanyWebsite` / `CompanyCareersUrl` / `JobsScrape` (`cost_eur` +
`input_tokens` / `output_tokens` from the Haiku call, null when no LLM call ran).
`scrape` and `geocode` are free.

### Response schemas

Response models live in `schemas/`, separate from ORM models, built with
`ConfigDict(from_attributes=True)` + `model_validate(obj)`.

**`CompanyRead`** — `kvk_number`, `names: CompanyNameRead[]`,
`addresses: AddressRead[]`.

**`CompanyNameRead`** — `name`, `type` (`statutory`/`trade`/`short`/`alias`).

**`AddressRead`** — `street?`, `house_number?`, `postcode?`, `city?`, `country`,
`lat?`, `lon?`, `geocoded_at?` (ISO-8601).

**`WebsiteSearchDetail`** — `id`, `query`, `status` (`success`/`failed`),
`error?`, `results?` (raw Serper JSON), `cost_eur?`, `created_at`.

**`WebsiteRead`** — `id`, `source_search_id`, `url?`, `homepage_url?`,
`confidence` (`high`/`medium`/`low`/`none`), `reason`, `llm_model`, `cost_eur?`,
`input_tokens?`, `output_tokens?`, `created_at`.

**`WebsiteScrapeRead`** — `id`, `source_website_id`, `status`,
`pages_attempted`, `pages_ok`, `pages_failed`, `error?`, `started_at`,
`finished_at?`, `created_at`, `pages: WebsitePageRead[]`.

**`WebsitePageRead`** — `id`, `url`, `normalized_url`, `fetch_method`, `status`,
`http_status?`, `content_type?`, `content_hash?`, `title?`, `markdown?`,
`fetched_at`. (`html_path` is internal — not exposed.)

**`CompanyCareersUrlRead`** — `id`, `source_scrape_id`, `url?`, `confidence`,
`reason`, `llm_model`, `cost_eur?`, `input_tokens?`, `output_tokens?`,
`created_at`.

**`JobsScrapeRead`** — `id`, `source_careers_id`, `fetched_url`, `status`,
`http_status?`, `content_hash?`, `llm_model?`, `cost_eur?`, `input_tokens?`,
`output_tokens?`, `error?`, `started_at`, `finished_at?`, `created_at`,
`jobs: JobRead[]`. (`html_path` not exposed.)

**`JobRead`** — `id`, `title`, `url?`, `careers_url`, `location?`,
`employment_type` (`full_time`/`part_time`/`contract`/`internship`/`unknown`),
`department?`, `raw_snippet?` (≤ 400 chars), `created_at`.

---

## 6. Roadmap

Scale context (not a current constraint): ~2M companies eventually qualify for
enrichment; re-enrichment cadence at scale is roughly monthly (jobs churn faster
than corporate metadata, but weekly is overkill). Everything below is built to
run inline at small scale today and port into a worker unchanged.

### Worker & queue

Move enrichment off the request path. Add `EnrichmentJob` (status:
`queued`/`running`/`done`/`failed`, `method`, `error`, `rq_job_id`) and wire an
**RQ** worker against the Redis already in compose. A `POST .../enrich`
dispatcher enqueues per-method jobs and returns `202`. The existing provider
packages (`serper/`, `llm/`, `pdok/`, `scraper/`, `jobs/`) port over untouched.

### Website scrape — later slices

- **1b — subpage discovery.** Re-introduce homepage link extraction + scoring in
  `scraper/discover.py` (`<nav>`/`<header>`/`<footer>` links, keyword set:
  `contact`, `over`, `about`, `vacature`, `werken`, `job`, `career`, `team`,
  `bedrijf`), union with a fallback path list, cap ~10 pages, concurrency ~3.
  Scrape status gains `partial` semantics.
- **2 — Tier 2 escalation.** When Tier 1 returns `js_required`/`blocked`, route
  through an external provider behind the same `fetch(url) -> FetchResult`
  interface (default **Jina Reader** `https://r.jina.ai/<url>`; Firecrawl /
  ScrapingBee / Playwright are additive). The `fetch_method` enum already has
  the slots — no schema change.

### Jobs — later slices

- **2 — ATS / external-domain careers pages.** Add an ATS hostname allowlist with
  vendor detection; extend `CompanyCareersUrl` with `is_external_ats` +
  `ats_vendor` (additive); candidate builder includes known ATS hosts; one-level
  iframe follow for company-domain pages embedding an ATS.
- **3 — Tier-2 rescue** for JS-heavy careers pages (depends on scrape Tier 2).
- **Later:** PDF job listings, cross-scrape diff (new/removed/re-opened jobs),
  job canonicalization + dedupe, employer-branding/benefits extraction.

### KVK ingestion

Replace the manual seed with a real KVK search-API scraper/ingester
(`scraper/kvk.py` in the original sketch). Names, KVK numbers, addresses.

### Paid-API concerns

API tokens (generatable), per-call logging/storage, billing. Deliberately
deferred until the enrichment core is validated.

### Alembic

Introduced once the schema stabilizes and there's data worth preserving across
changes. Until then: iterate freely, drop the volume, re-seed.

### Downstream extraction (beyond jobs)

The stored markdown corpus feeds further LLM passes — contact extraction, company
summarization, general structured enrichment — each as its own append-only slice
mirroring the jobs two-stage (locate → extract) pattern.

---

## 7. Design notes & open questions

### Decided

- **Two cheap LLM calls beat one expensive agent.** Splitting "find the URL" from
  "extract from the page" keeps each task narrow, cacheable, and debuggable. Each
  is Haiku 4.5 with a frozen, verbatim system prompt marked
  `cache_control: ephemeral`.
- **Browsing-agent approaches rejected** for extraction at 2M scale —
  non-determinism, cost, rate limits. Revisit only if the deterministic
  two-stage approach plateaus on recall.
- **Geocoding provider: PDOK** — free, Dutch-specific, BAG-backed. Address-level
  matches only.
- **LLM provider: Anthropic (Claude Haiku 4.5)** behind the `llm/` and `jobs/`
  packages so swapping is local.
- **Raw HTML on disk, markdown in Postgres** — see §4 storage decision.

### Open / revisit before scaling

- **Object storage for raw HTML** (R2/S3) — `html_path` becomes an object key;
  swap the filesystem writer behind the same interface.
- **GDPR / data retention policy** — out of scope until validation.
- **Budget / cost caps** on LLM + Tier-2 provider calls — wire before full scale.
- **EnrichmentResult shape** when the worker lands — one JSONB table vs. the
  current per-method tables (we've leaned per-method so far).
- **Playwright packaging** if/when it's needed — dedicated worker image with
  browsers baked in, vs. a separate queue.
- **Auto-skip chronically failing domains** on the monthly re-scrape.
