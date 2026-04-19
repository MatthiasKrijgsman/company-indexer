# Jobs discovery and extraction plan

Plan for the enrichment slice that turns a scraped homepage into a list
of open job positions (if any). Consumes what `plan-scrape.md` produces;
feeds future downstream passes (contact extraction, summarization).

Read this alongside `mvp-plan.md`, `initial-plan.md`, `plan-scrape.md`.
If anything here conflicts with those, raise it.

## Context

### What's already in place

- `POST /companies/{kvk}/scrape` fetches the homepage, persists HTML to
  disk under `SCRAPED_HTML_DIR`, and stores extracted markdown + a title
  on a `WebsitePage` row.
- `CompanyWebsite.homepage_url` is the upstream anchor.

A company with no successful homepage scrape is not a candidate for
this slice — `js_required` / `blocked` / `failed` scrapes get skipped
until the scraper's Tier 2 slice lands.

### Goal

For each company with an `OK` homepage scrape:

1. Identify the careers page (if any) — the URL where open positions
   are listed. Often it's on the company's own domain, often it isn't
   (ATS platforms host the real page under their own domain).
2. Fetch that page and extract structured job postings.
3. Persist the attempt — including "no careers page" and "careers page
   exists but no open roles" as first-class outcomes.

Downstream consumers (search, UI, alerting) will read `Job` rows.

### Scale and cadence

- ~2M companies eventually. Re-run cadence: monthly once at scale
  (jobs churn faster than corporate metadata, but weekly is overkill).
- Small scale initially, inline in request handlers.
- Designed so the same code ports into a worker without rework.

### Constraints and preferences

- **Two cheap LLM calls beat one expensive agent.** Splitting "find the
  careers URL" from "extract jobs from this page" keeps both tasks
  narrow, cacheable, and individually debuggable. Each call is Haiku
  4.5 with a frozen system prompt.
- **Company's own domain only, for now.** External ATS platforms
  (Recruitee, Homerun, Workable, etc.) are out of scope for this slice
  — careers pages not on the company's registered website domain are
  treated as "no careers page" and persisted as such. Revisit once
  same-domain extraction is validated.
- **Null is a valid result at both stages.** Many Dutch SMBs don't
  publish a careers page at all on their own site (many use an ATS,
  which we're ignoring for now). Record the attempt with
  `status="no_careers_page"` and move on.
- **Never raise on provider failures.** Same pattern as `serper/`,
  `llm/`, `pdok/`: typed result with `ok` + `error` code.
- **Append-only history.** Each attempt inserts new rows; we never
  overwrite. Queries are always "latest by created_at".
- **Browsing-agent approaches explicitly rejected for this slice.**
  Non-determinism, cost, and rate limits disqualify web-browsing LLM
  tools at 2M-company scale. Revisit only if the two-stage approach
  plateaus at unacceptable recall.
- GDPR, retention, budget — same posture as `plan-scrape.md`: out of
  scope until validation.

## Strategy

Two stages, mirroring the existing `website-search` → `resolve-website`
split:

1. **Locate** the careers URL (`POST /companies/{kvk}/resolve-careers`).
2. **Extract** the jobs on that URL (`POST /companies/{kvk}/scrape-jobs`).

Each stage persists its own row and can be re-run independently.

### Stage A — Locate the careers URL

Input: the latest `OK` `WebsiteScrape` for the company. We need the
homepage HTML's link set and the resolved `homepage_url`.

**Candidate building** — deterministic, no LLM, same-domain only:

1. Parse homepage HTML (load from disk via `WebsitePage.html_path`).
2. Collect same-domain `<a>` links whose path + anchor text match a
   small keyword set: `vacature`, `vacatures`, `werken`, `werken-bij`,
   `jobs`, `job`, `career`, `careers`. Score by keyword weight.
3. Add a small fallback path list on the company's own domain
   (`/vacatures`, `/werken-bij`, `/careers`) so image-only or
   JS-rendered navs still contribute.
4. Dedupe (via `scraper.discover.normalize_url`), cap at ~10 candidates.

Cross-domain links (to ATS hosts like `*.recruitee.com` or similar) are
dropped at this stage. Future slices will add them back.

**LLM pick** — Claude Haiku 4.5, `messages.parse` with a Pydantic
output model. Input: company name(s), city, homepage URL, candidate
list with anchor text. Output: `chosen_url`, `confidence`
(`high`/`medium`/`low`), `reason`. Returns `null` when no candidate is
confidently the careers page.

When candidate list has exactly one entry on a fallback path the
picker LLM is still called — we don't auto-accept a guessed URL
without confirmation that the page actually exists and looks like a
careers page. The fetch in Stage B is the real validator.

**Persist:** new `CompanyCareersUrl` row. Append-only history. Even a
null result is persisted (`confidence=none`, `reason` explains why).

### Stage B — Extract jobs from the careers URL

Input: the latest `CompanyCareersUrl` with non-null `url`.

**Fetch** — reuse `scraper/fetch.py` + `scraper/extract.py` +
`scraper/storage.py` as a library:

1. Build the same-browser-profile httpx client.
2. Fetch the careers URL.
3. Classify via `scraper.detect`. Blocked / js_required short-circuits
   the scrape; the LLM isn't called.
4. On success: save HTML to disk, extract markdown.

Iframe follow (ATS embeds) is out of scope for this slice — an
iframe-driven careers page with near-empty markdown will be recorded
as `js_required` or `no_jobs` and picked up by a future slice.

**LLM extract** — Haiku 4.5, frozen system prompt, `messages.parse`
with `list[Job]` output. Feed the page's markdown (clipped to a
reasonable token budget) and the company context. Output schema per
job: `title` (required), `url` (nullable — the per-posting detail URL
when visible in the listing), `location`, `employment_type`
(`full_time` / `part_time` / `contract` / `internship` / `unknown`),
`department`, `raw_snippet` (the markdown fragment the job was
extracted from, for debugging).

**Persist:** one `JobsScrape` row, plus one `Job` row per extracted
position. When the LLM returns an empty list but the page fetched
cleanly, `JobsScrape.status = "no_jobs"` — the company *has* a
careers page, no roles are open. This is a valid, useful state.

## Schema

Three new tables, matching the append-only convention.

### `CompanyCareersUrl`

One row per resolution attempt per company.

| Field               | Type                                                       |
|---------------------|------------------------------------------------------------|
| `id`                | int PK                                                     |
| `company_id`        | FK → `companies.id`, cascade, indexed                      |
| `source_scrape_id`  | FK → `website_scrapes.id`, cascade — the scrape whose homepage HTML was read |
| `url`               | String(2048), nullable — null means no careers page found on the company's own domain |
| `confidence`        | enum (reuse `website_confidence`): `high`/`medium`/`low`/`none` |
| `reason`            | String(512) — short LLM rationale, or error code           |
| `llm_model`         | String(64)                                                 |
| `created_at`        | timestamptz, server default `now()`                        |

No new enum — `website_confidence` already has the right shape.

### `JobsScrape`

One row per extraction attempt per company.

| Field                | Type                                                       |
|----------------------|------------------------------------------------------------|
| `id`                 | int PK                                                     |
| `company_id`         | FK → `companies.id`, cascade, indexed                      |
| `source_careers_id`  | FK → `company_careers_urls.id`, cascade                    |
| `fetched_url`        | String(2048) — the URL actually fetched                    |
| `status`             | enum: `ok`, `no_jobs`, `no_careers_page`, `js_required`, `blocked`, `failed`, `llm_error` |
| `http_status`        | int, nullable                                              |
| `content_hash`       | String(64), nullable — sha256 of the markdown used for extraction |
| `html_path`          | String(512), nullable — same filesystem convention as `WebsitePage` |
| `llm_model`          | String(64), nullable                                       |
| `error`              | String(64), nullable                                       |
| `started_at`         | timestamptz                                                |
| `finished_at`        | timestamptz, nullable                                      |
| `created_at`         | timestamptz, server default `now()`                        |

New enum: `jobs_scrape_status_enum`.

### `Job`

One row per extracted position per scrape. Append-only — "how did the
job set change?" is a cross-scrape diff question for later.

| Field              | Type                                                       |
|--------------------|------------------------------------------------------------|
| `id`               | int PK                                                     |
| `jobs_scrape_id`   | FK → `jobs_scrapes.id`, cascade, indexed                   |
| `title`            | String(512)                                                |
| `url`              | String(2048), nullable                                     |
| `location`         | String(255), nullable                                      |
| `employment_type`  | enum: `full_time`, `part_time`, `contract`, `internship`, `unknown` |
| `department`       | String(255), nullable                                      |
| `raw_snippet`      | text, nullable                                             |
| `created_at`       | timestamptz, server default `now()`                        |

New enum: `job_employment_type_enum`.

**Storage decision:** markdown is used at extraction time but not
stored on `JobsScrape` — it's a transient input, not a corpus. The
careers page's HTML is saved to disk so re-extraction with an improved
prompt is cheap; that's what `html_path` on `JobsScrape` is for.

## Endpoints

Per-action, matches existing patterns. Document in `docs.md`.

### `POST /companies/{kvk_number}/resolve-careers`

Reads the latest `OK` `WebsiteScrape`, builds candidates, runs the
picker, inserts a new `CompanyCareersUrl` row.

- `200 OK` — `CompanyCareersUrlRead`.
- `400 Bad Request` — no OK scrape on record (call `/scrape` first).
- `404 Not Found` — unknown company.
- `502 Bad Gateway` — LLM provider failure. Row still written with
  `confidence=none`, `reason="resolver_error: ..."`.

### `GET /companies/{kvk_number}/careers-url`

Latest careers-URL resolution, including the `null` outcome.

### `POST /companies/{kvk_number}/scrape-jobs`

Reads the latest `CompanyCareersUrl` with non-null `url`, fetches it
(with one-level iframe follow), runs the extractor, inserts a
`JobsScrape` + `Job` children.

- `200 OK` — `JobsScrapeRead` with jobs inlined. Non-terminal outcomes
  (`no_jobs`, `js_required`, `blocked`) are 200s — status is in the
  body.
- `400 Bad Request` — no careers URL on record.
- `404 Not Found` — unknown company.

### `GET /companies/{kvk_number}/jobs`

Latest `JobsScrape` with jobs inlined.

### `GET /companies/{kvk_number}/jobs-history`

List of `JobsScrape`, newest first. Parallels `/scrapes`.

### Response schemas

`CompanyCareersUrlRead`, `JobsScrapeRead`, `JobRead`. Standard repo
pattern: `ConfigDict(from_attributes=True)` + `model_validate(obj)`.
`JobsScrapeRead` omits `html_path` (internal detail, same rule as
`WebsitePageRead`).

## Package layout

```
src/company_indexer/jobs/
├── __init__.py
├── candidates.py   — build candidate careers URLs from homepage HTML (same-domain only)
├── resolver.py     — Claude Haiku call, Pydantic output
├── extractor.py    — Claude Haiku call, list[Job] structured output
└── orchestrator.py — per-company resolve + scrape-jobs entrypoints
```

Each module mirrors the `serper/` / `llm/` / `pdok/` convention:
async functions returning typed dataclasses, never raising on provider
errors.

## Failure handling

Status codes carry the truth; no separate log table.

Stage A (`CompanyCareersUrl`):
- No candidates on homepage → `url=null`, `reason="no_candidates"`.
- LLM returns null → `url=null`, `reason` is the LLM rationale.
- LLM API failure → `url=null`, `reason="resolver_error: ..."`.

Stage B (`JobsScrape`):
- Careers page fetch blocked / 4xx / 5xx → `status="blocked"` or
  `"failed"`, `error` is the fetch code.
- Careers page is JS-heavy → `status="js_required"`. No LLM call.
- Fetch OK, LLM extracts empty list → `status="no_jobs"`.
- Fetch OK, LLM extracts N > 0 jobs → `status="ok"`.
- LLM API failure on an otherwise-OK fetch → `status="llm_error"`.

Companies with `CompanyCareersUrl.url=null` are short-circuited at
Stage B entry: `status="no_careers_page"`, no fetch, no LLM call.

## Slicing

### Slice 1 — company-domain only

- `jobs/` package: candidates, resolver, extractor, orchestrator.
- Schema: all three tables, two new enums.
- Reseed required.
- Routes: `/resolve-careers`, `/careers-url`, `/scrape-jobs`, `/jobs`,
  `/jobs-history`.
- `docs.md` updated.

### Slice 2 — ATS / external-domain careers pages

- Add ATS hostname allowlist with vendor detection.
- Extend `CompanyCareersUrl` with `is_external_ats` + `ats_vendor`
  (additive migration when we get there).
- Candidate builder includes cross-domain links to known ATS hosts.
- Picker LLM sees vendor tag as a signal; deterministic shortcut when
  exactly one unambiguous ATS link is present.
- Iframe follow for company-domain pages that embed an ATS under
  their own URL.

### Slice 3 — Tier 2 rescue for JS-heavy careers pages

- When a careers-page fetch yields `js_required`, route through the
  scraper's (future) Tier 2 provider. Depends on `plan-scrape.md`
  Tier 2 landing first.

### Later (not planned yet)

- PDF job listings (fetch, extract text, same extractor prompt).
- Cross-scrape diff: new jobs, removed jobs, re-opened jobs.
- Job canonicalization + dedupe.
- Employer branding / benefits extraction from the careers page.

## Out of scope for this plan

- KVK ingestion, billing, Alembic — per `mvp-plan.md`.
- Worker / RQ — sync inline, same as all other enrichers.
- GDPR / retention — revisit before scaling.
- Budget caps — revisit before running at full scale.
- Image-only job listings.
- Browser-automation extraction (Playwright) — deferred with Tier 2.
