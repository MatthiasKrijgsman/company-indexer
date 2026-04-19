# Website scraping plan

Plan for the next enrichment slice: given a company with a resolved
`CompanyWebsite.homepage_url`, scrape that site and store the content so downstream
steps (jobs extraction, contact extraction, general LLM-based enrichment)
have something to work on.

Read this alongside `mvp-plan.md` and `initial-plan.md`. If anything here
conflicts with those, raise it.

## Context

### What's already in place

- `POST /companies/{kvk}/website-search` runs a Serper search and stores
  the raw response.
- `POST /companies/{kvk}/resolve-website` picks the homepage via Claude
  Haiku 4.5 and stores a `CompanyWebsite` row with `url` and
  `homepage_url` (or `null` when no confident match).

The scrape step picks up from the resolved homepage URL. A company with
no successful resolution (or `url=null`) is skipped — nothing to scrape.

### Goal

For each company with a resolved website:

1. Fetch the homepage and a handful of relevant internal pages
   (contact, about, jobs/vacatures, team).
2. Extract clean markdown per page and persist it, alongside enough
   metadata to re-fetch, diff, and debug later.
3. Record failures explicitly — blocked, JS-heavy, dead domain, timeout
   — so we can act on them (retry next month, escalate to a browser-based
   fetcher, give up).

Downstream LLM passes will consume the stored markdown. They are **not**
part of this slice.

### Scale and cadence (for context, not MVP)

- ~2M companies eventually qualify for scraping.
- Re-scrape cadence once it runs at scale: monthly.
- At small scale initially (hundreds to low thousands) while the
  pipeline is being validated.

This slice is built to run at small scale inline, but the schema and
package layout are designed so the same code ports into a worker later
without rework.

### Constraints and preferences

- **Low cost but reliable.** Try hard to get the page with plain HTTP
  before reaching for a paid provider.
- **Replicate a real browser** at the HTTP layer — realistic User-Agent,
  full header set, cookies, HTTP/2, redirect following.
- **When HTTP can't do it, escalate to an external provider.** Not part
  of slice 1; schema leaves room for it.
- **Failures are logged as status, not thrown away.** A blocked page is
  a valid scrape outcome, not an error.
- **Latency is not a constraint.** Scrape can take minutes per company.
- **No worker yet.** Runs inline in the request handler, like the other
  enrichment endpoints. Will port to RQ later (no code changes in
  `scraper/` expected when that happens).
- GDPR, retention, and budget are out of scope for this slice — to be
  revisited before going to real scale.

## Fetch strategy

### Tier 1 — httpx with a real-browser profile

Default path. Free, fast, good enough for most Dutch SMB sites
(WordPress-heavy).

**Headers and client setup:**

- Rotate through 2–3 current-stable User-Agents (Chrome-macOS,
  Chrome-Windows, Firefox-Windows). Pick one deterministically per
  scrape (hash of company id) so behavior is reproducible.
- Full header set matching the chosen UA:
  - `Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8`
  - `Accept-Language: nl-NL,nl;q=0.9,en;q=0.8`
  - `Accept-Encoding: gzip, deflate, br`
  - `sec-ch-ua` family matching the UA
  - `Upgrade-Insecure-Requests: 1`, `DNT: 1`
- `httpx.AsyncClient` with `http2=True`, `follow_redirects=True`, a
  cookie jar scoped to the scrape (some sites set a session cookie on
  `/` that later paths require).
- Timeouts: ~10s connect, 20s read. Retry once on transient network
  errors; do not retry on 4xx/5xx.

### JS / block detection

After each Tier-1 response, check for signals that the page needs a
browser. If any hit, mark the page `js_required` or `blocked` (don't
try harder in slice 1):

- Status `403` / `503` with Cloudflare/Datadome markers in body
  (`cf-chl`, `__cf_bm`, `datadome`) → `blocked`.
- Status `200` but body is a JS skeleton: `<div id="root">` /
  `<div id="app">` / `<div id="__next">` present AND extracted text
  < ~200 chars → `js_required`.
- Status `200` with very small body (< 2KB) and `<noscript>` mentioning
  "enable JavaScript" → `js_required`.
- Meta refresh or JS-only redirect (`<meta http-equiv="refresh">`, or
  `window.location` in a `<script>`) with no static content →
  `js_required`.

### Tier 2 — external provider (slice 2, not now)

Deferred. When built:

- Default to **Jina Reader** (`https://r.jina.ai/<url>`) — free tier
  for small scale, returns markdown directly, handles JS.
- Implement as a pluggable strategy behind the same
  `async def fetch(url) -> FetchResult` interface so swapping
  Firecrawl / ScrapingBee / Playwright later is additive, not a
  migration.
- Orchestrator decides Tier 2 per-page based on Tier 1's verdict or on
  a previous scrape's recorded status for that URL.

For slice 1: pages with `status=js_required` or `status=blocked` are
persisted and skipped. No retry, no fallback.

## Page discovery per company

Slice 1b: **homepage only.** Fetch `CompanyWebsite.homepage_url` and
nothing else. Discovery (nav/footer link extraction, keyword scoring,
fallback path list) is deferred to a later slice — the homepage is the
minimum viable corpus for the downstream LLM passes, and avoiding
subpage fans-out also makes per-company rate and blast radius predictable
for the eventual worker.

When subpage discovery is added back:

- Parse homepage HTML for same-domain `<a>` links in `<nav>`, `<header>`,
  `<footer>`, and top-of-body.
- Score each link's path + anchor text against a small keyword set
  (`contact`, `over`, `about`, `vacature`, `werken`, `job`, `career`,
  `team`, `bedrijf`). Keep the top ~8.
- Union with a small fallback path list (`/contact`, `/vacatures`,
  `/over-ons`) for image-based or JS navs.
- Dedupe, cap at ~10 pages, fetch with concurrency ~3.

## Schema

Two new tables, matching the `WebsiteSearch` / `CompanyWebsite`
convention (append-only history; native Postgres enums declared once
and reused).

### `WebsiteScrape`

One row per scrape attempt per company.

| Field               | Type                                                       |
|---------------------|------------------------------------------------------------|
| `id`                | int PK                                                     |
| `company_id`        | FK → `companies.id`, cascade, indexed                      |
| `source_website_id` | FK → `company_websites.id`, cascade                        |
| `status`            | enum: `ok`, `partial`, `failed`, `skipped_no_website`, `skipped_js_heavy`, `skipped_dead_domain` |
| `pages_attempted`   | int                                                        |
| `pages_ok`          | int                                                        |
| `pages_failed`      | int                                                        |
| `error`             | String(64), nullable — short code (convention: `timeout`, `network_error`, `all_blocked`, etc.) |
| `started_at`        | timestamptz                                                |
| `finished_at`       | timestamptz, nullable                                      |
| `created_at`        | timestamptz, server default `now()`                        |

New enum: `website_scrape_status_enum`.

### `WebsitePage`

One row per URL × scrape.

| Field              | Type                                                       |
|--------------------|------------------------------------------------------------|
| `id`               | int PK                                                     |
| `scrape_id`        | FK → `website_scrapes.id`, cascade, indexed                |
| `url`              | String(2048)                                               |
| `normalized_url`   | String(2048) — lowercased host, trailing slash normalized  |
| `fetch_method`     | enum: `http`, `jina`, `firecrawl`, `playwright` (slice 1: `http` only) |
| `status`           | enum: `ok`, `http_4xx`, `http_5xx`, `timeout`, `network_error`, `js_required`, `blocked`, `dead_domain`, `non_html` |
| `http_status`      | int, nullable                                              |
| `content_type`     | String(128), nullable                                      |
| `content_hash`     | String(64), nullable — sha256 of normalized markdown       |
| `title`            | String(512), nullable                                      |
| `markdown`         | text, nullable                                             |
| `html_path`        | String(512), nullable — filesystem path (relative to the scraped-html root) to the raw HTML file; null when fetch didn't produce HTML |
| `fetched_at`       | timestamptz                                                |

Indexes:

- `UniqueConstraint(scrape_id, normalized_url)`.
- `Index(company_id, url, content_hash)` for future cross-scrape diff
  queries (added via standalone `Index(...)` calls, per the repo
  convention).

New enums: `website_page_fetch_method_enum`, `website_page_status_enum`.

**Storage decision:** markdown lives in Postgres (`WebsitePage.markdown`).
Raw HTML lives on the server's filesystem under a configurable root —
default `data/scraped_html/` — laid out as
`data/scraped_html/{company_id}/{scrape_id}/{page_id}.html`. The
`WebsitePage.html_path` column stores the path **relative to the root**
so the root can move (different env, object storage later) without a
data migration.

Rationale: keeping HTML out of Postgres avoids row-size and backup
bloat at any real volume; keeping it on disk (vs. discarded) means we
can re-run a better extractor later without re-fetching. The
filesystem root is gitignored (see `.gitignore`). When scale demands
it, swap the filesystem writer for an object-storage writer behind the
same interface and start populating a new column / reusing
`html_path` as a key — no schema migration beyond that.

Writes happen inside `orchestrator.scrape_company` after a successful
fetch, before the `WebsitePage` row is committed — if the filesystem
write fails, the page is recorded as `network_error` / a dedicated
code and `html_path` stays null. Compression (gzip) is deferred; files
are written as plain `.html` in slice 1.

## Endpoints

Per-action, matches the existing pattern. Document these in `docs.md`
when implemented.

### `POST /companies/{kvk_number}/scrape`

Reads the latest `CompanyWebsite` with non-null `homepage_url`, runs the scraper,
always inserts a new `WebsiteScrape` + child `WebsitePage` rows.

- `200 OK` with a summary body, even when content-level things go wrong
  (blocked, js_required, partial). Status is in the response body, not
  the HTTP code.
- `400 Bad Request` — no resolved website (call `/resolve-website`
  first).
- `404 Not Found` — unknown company.
- `502 Bad Gateway` — reserved for slice 2 (genuine Tier-2 provider
  infra failures). Not used in slice 1.

### `GET /companies/{kvk_number}/scrape`

Latest scrape for the company, with the page list inlined.

- `200 OK` — `WebsiteScrapeRead` with pages.
- `404 Not Found` — unknown company, or no scrape has been run yet.

### `GET /companies/{kvk_number}/scrapes`

History, newest first. Parallels `GET /companies/{kvk}/website-search`.

- `200 OK` — `WebsiteScrapeRead[]`.
- `404 Not Found` — unknown company.

### Response schemas

`WebsiteScrapeRead`, `WebsitePageRead`. Define in
`schemas/website_scrape.py`. Use `ConfigDict(from_attributes=True)` +
`model_validate(obj)` per repo convention. `WebsitePageRead` omits
`html_path` — the filesystem layout is an internal detail, and
exposing paths invites path-traversal mistakes downstream. A future
endpoint can stream the raw HTML by `(scrape_id, page_id)` if needed.

## Package layout

Follows the `serper/` / `pdok/` / `llm/` pattern: external-facing
package with small focused modules, each exposing an async function
that returns a typed dataclass with `ok: bool` + `error: str | None` +
payload. Never raise on HTTP errors — caller inspects `ok`.

```
src/company_indexer/scraper/
├── __init__.py
├── headers.py       — UA rotation + header builder
├── fetch.py         — Tier 1: httpx client → FetchResult(ok, status, html, error)
├── detect.py        — JS-skeleton / WAF-block heuristics → Verdict
├── extract.py       — trafilatura wrapper → (markdown, title)
├── discover.py      — URL normalization (subpage discovery deferred)
├── storage.py       — filesystem writer: save raw HTML under the scraped-html root, return relative path
└── orchestrator.py  — per-company scrape loop, commits rows
```

The scraped-html root is read from settings (new `SCRAPED_HTML_DIR`,
default `data/scraped_html`) via the existing `config.py`. Directory
is created on first write. `storage.py` is the only module that
touches the filesystem; `orchestrator.py` calls it and stores the
returned relative path on the `WebsitePage` row.

The endpoint calls `orchestrator.scrape_company(session, company,
website)`. Everything else is internal.

## Failure handling

Everything gets persisted. The status enums are the log; no separate
log table.

- Homepage OK → `WebsiteScrape.status = 'ok'`, `pages_ok = 1`.
- Homepage times out / 403 / 5xx / DNS fails → `WebsiteScrape.status =
  'failed'` with a short `error` code copied from the page status; the
  `WebsitePage` row is still written so the failure is observable.
- Dead domain (DNS NXDOMAIN, connection refused) →
  `status = 'skipped_dead_domain'`. Caller decides if/when to retry; we
  don't auto-skip chronic failures yet.
- JS-heavy homepage → `status = 'skipped_js_heavy'`. Homepage
  `WebsitePage` row still written with `status = 'js_required'`.

When subpage discovery is reintroduced, per-page failures will also bump
`WebsiteScrape.pages_failed` and `status` may become `'partial'`.

The monthly re-scrape (future) can look at the previous scrape's page
statuses and route `js_required` URLs straight to Tier 2 without
re-probing Tier 1. The schema supports this; the logic is slice 2+.

## Slicing

### Slice 1 — Tier 1, homepage only

- `scraper/` package: headers, fetch, detect, extract, storage,
  orchestrator (+ a thin `discover.py` for URL normalization).
- Schema: `WebsiteScrape`, `WebsitePage`, three new enums.
- Reseed required (`docker compose down -v && docker compose up -d`
  + `python -m company_indexer.scripts.seed_companies`).
- Routes: `POST /companies/{kvk}/scrape`, `GET .../scrape`,
  `GET .../scrapes`.
- Response schemas: `WebsiteScrapeRead`, `WebsitePageRead`.
- Raw HTML persisted under `data/scraped_html/` (configurable via
  `SCRAPED_HTML_DIR`); path stored in `WebsitePage.html_path`. Root
  directory added to `.gitignore`.
- `docs.md` updated.
- No subpage discovery, no Tier 2, no object storage, no worker, no
  re-scrape logic.

### Slice 1b — subpage discovery

- Re-introduce homepage link extraction + scoring in `scraper/discover.py`.
- Orchestrator fetches subpages with concurrency ~3 per company.
- Scrape status gains `'partial'` semantics (some pages OK, some failed).

### Slice 2 — Tier 2 escalation

- `scraper/jina.py` implementing the same `fetch(url)` interface.
- Orchestrator decides Tier 1 vs Tier 2 per page.
- No schema changes (the `fetch_method` enum already has the slots).
- `docs.md` updated to note escalation behavior.

### Later (not planned yet)

- Object storage for raw HTML (migrate from filesystem to R2 / S3;
  `html_path` becomes an object key).
- Scheduled monthly re-scrape via worker.
- Cross-scrape change detection (skip unchanged pages via
  `content_hash`).
- Auto-skip chronically failing domains.
- Downstream LLM extractors (jobs, contacts) reading `markdown` from
  `WebsitePage`.

## Out of scope for this plan

- KVK ingestion, API tokens, billing, Alembic — per `mvp-plan.md`.
- Worker / RQ — sync inline for now, same as other enrichers.
- GDPR / retention policy — revisit before scaling beyond validation.
- Budget limits / cost caps — revisit before wiring Tier 2.
- Downstream extraction (jobs, contacts, etc.) — separate future slices.
