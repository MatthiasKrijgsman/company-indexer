# API docs

HTTP API for Dutch company (KVK) data. No auth yet — local only.

Base URL: `http://localhost:8000`

## Endpoints

### `GET /companies`

List companies with optional substring search on any associated name.

Query parameters:

| Name     | Type     | Default | Description                                     |
|----------|----------|---------|-------------------------------------------------|
| `limit`  | int      | `50`    | Page size, `1`–`200`.                           |
| `offset` | int      | `0`     | Rows to skip.                                   |
| `q`      | string   | —       | Case-insensitive substring match on any name.   |

Response: `200 OK`

```json
{
  "items": [
    {
      "kvk_number": "12345678",
      "names": [{ "name": "Acme B.V.", "type": "statutory" }],
      "addresses": [
        {
          "street": "Damrak",
          "house_number": "1",
          "postcode": "1012LG",
          "city": "Amsterdam",
          "country": "NL",
          "lat": "52.3740",
          "lon": "4.8897"
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

Path parameters:

| Name         | Type   | Description           |
|--------------|--------|-----------------------|
| `kvk_number` | string | KVK registration nr.  |

Responses:

- `200 OK` — single `CompanyRead` object (same shape as `items[]` above).
- `404 Not Found` — no company with that KVK number.

### `POST /companies/{kvk_number}/website-search`

Runs a Google search (via Serper) for `kvk "{kvk_number}"` with known
business-registry aggregators excluded, and stores the raw result. Intended
as the first step in finding a company's own website — picking the winning
URL from the stored results is left to a future enrichment step.

The attempt is persisted whether it succeeds or fails.

Path parameters:

| Name         | Type   | Description           |
|--------------|--------|-----------------------|
| `kvk_number` | string | KVK registration nr.  |

Responses:

- `200 OK` — `WebsiteSearchDetail` (raw Serper JSON inlined under `results`).
- `404 Not Found` — no company with that KVK number.
- `502 Bad Gateway` — Serper call failed (timeout, network error, no credits,
  unauthorized, or non-200 response). The attempt row is still written with
  `status="failed"`.

### `GET /companies/{kvk_number}/website-search`

Returns every website-search attempt for the given company, newest first,
with the raw Serper response JSON inlined. Empty list if the company exists
but no searches have been run yet.

Path parameters:

| Name         | Type   | Description           |
|--------------|--------|-----------------------|
| `kvk_number` | string | KVK registration nr.  |

Responses:

- `200 OK` — `WebsiteSearchDetail[]`.
- `404 Not Found` — no company with that KVK number.

### `POST /companies/{kvk_number}/resolve-website`

Reads the latest successful `WebsiteSearch` for this company and asks an
LLM (Claude Haiku 4.5) to pick the candidate most likely to be the
company's own primary website. The LLM sees Serper metadata only (titles,
URLs, snippets) — it does not fetch candidate pages.

Always inserts a new `CompanyWebsite` row (history is preserved across
re-resolutions). The LLM may return `url=null` when no candidate is
confidently the company's site — that is a valid outcome.

Path parameters:

| Name         | Type   | Description           |
|--------------|--------|-----------------------|
| `kvk_number` | string | KVK registration nr.  |

Responses:

- `200 OK` — `WebsiteRead` (see below).
- `400 Bad Request` — no successful website search on record. Call
  `POST /companies/{kvk_number}/website-search` first.
- `404 Not Found` — no company with that KVK number.
- `502 Bad Gateway` — the LLM call failed. A row is still written with
  `confidence="none"` and `reason="resolver_error: ..."` so the attempt is
  visible via `GET /companies/{kvk_number}/website`.

### `GET /companies/{kvk_number}/website`

Returns the most recent website resolution for the given company.

Path parameters:

| Name         | Type   | Description           |
|--------------|--------|-----------------------|
| `kvk_number` | string | KVK registration nr.  |

Responses:

- `200 OK` — `WebsiteRead`.
- `404 Not Found` — no company with that KVK number, or no resolution has
  been run yet.

### `POST /companies/{kvk_number}/scrape`

Scrapes the company's homepage (the latest `CompanyWebsite.homepage_url`).
The homepage is classified, its raw HTML is persisted to disk under
`SCRAPED_HTML_DIR`, and its extracted markdown + metadata are stored in the
database. Always inserts a new `WebsiteScrape` row plus exactly one
`WebsitePage` child for the homepage.

Page-level outcomes (blocked, js_required, timeout, etc.) are recorded as
`WebsitePage.status` — the endpoint still returns `200 OK` for those. Only
protocol-level preconditions return non-2xx.

Path parameters:

| Name         | Type   | Description           |
|--------------|--------|-----------------------|
| `kvk_number` | string | KVK registration nr.  |

Responses:

- `200 OK` — `WebsiteScrapeRead` with the `pages` array.
- `400 Bad Request` — no resolved `CompanyWebsite.homepage_url` on record. Call
  `POST /companies/{kvk_number}/resolve-website` first.
- `404 Not Found` — no company with that KVK number.

### `GET /companies/{kvk_number}/scrape`

Returns the most recent scrape for the company, with the page list inlined.

Path parameters:

| Name         | Type   | Description           |
|--------------|--------|-----------------------|
| `kvk_number` | string | KVK registration nr.  |

Responses:

- `200 OK` — `WebsiteScrapeRead`.
- `404 Not Found` — unknown company, or no scrape has been run yet.

### `GET /companies/{kvk_number}/scrapes`

History of scrapes for the company, newest first. Each entry includes its
full `pages` list.

Path parameters:

| Name         | Type   | Description           |
|--------------|--------|-----------------------|
| `kvk_number` | string | KVK registration nr.  |

Responses:

- `200 OK` — `WebsiteScrapeRead[]`. Empty array when the company exists but
  has never been scraped.
- `404 Not Found` — no company with that KVK number.

### `POST /companies/{kvk_number}/resolve-careers`

Builds candidate careers-page URLs from the homepage HTML of the latest `OK`
`WebsiteScrape` (same-domain links keyword-scored against `vacature`, `werken`,
`jobs`, `career` + a small fallback path list), then asks Claude Haiku 4.5 to
pick the URL most likely to be the company's careers page. Always inserts a
new `CompanyCareersUrl` row. A null `url` with `confidence="none"` is a valid,
first-class outcome — most Dutch SMBs don't publish a same-domain careers page.

External ATS platforms (Recruitee, Homerun, etc.) are not considered in this
slice; any link off the company's own domain is dropped from the candidate list.

Path parameters:

| Name         | Type   | Description           |
|--------------|--------|-----------------------|
| `kvk_number` | string | KVK registration nr.  |

Responses:

- `200 OK` — `CompanyCareersUrlRead`.
- `400 Bad Request` — no `OK` website scrape on record. Call
  `POST /companies/{kvk_number}/scrape` first.
- `404 Not Found` — no company with that KVK number.
- `502 Bad Gateway` — the LLM call failed. A row is still written with
  `confidence="none"` and `reason="resolver_error: ..."` so the attempt is
  visible via `GET /companies/{kvk_number}/careers-url`.

### `GET /companies/{kvk_number}/careers-url`

Latest careers-URL resolution, including the null outcome.

Responses:

- `200 OK` — `CompanyCareersUrlRead`.
- `404 Not Found` — no company with that KVK number, or no resolution run yet.

### `POST /companies/{kvk_number}/scrape-jobs`

Fetches the latest resolved careers URL, extracts markdown, and runs Claude
Haiku 4.5 to enumerate open positions. Always inserts a new `JobsScrape` row
plus one `Job` child per extracted position. Page-level outcomes (`blocked`,
`js_required`, fetch failures) are carried on `JobsScrape.status` — the
endpoint still returns `200 OK`. An empty-but-clean careers page yields
`status="no_jobs"`; a null careers URL upstream is rejected with `400` rather
than written as `no_careers_page` (the null was already persisted at the
resolve step).

Path parameters:

| Name         | Type   | Description           |
|--------------|--------|-----------------------|
| `kvk_number` | string | KVK registration nr.  |

Responses:

- `200 OK` — `JobsScrapeRead` with the `jobs` array.
- `400 Bad Request` — no careers URL, or no `OK` upstream website scrape.
- `404 Not Found` — no company with that KVK number.

### `GET /companies/{kvk_number}/jobs`

Latest `JobsScrape` with jobs inlined.

Responses:

- `200 OK` — `JobsScrapeRead`.
- `404 Not Found` — unknown company, or no jobs scrape run yet.

### `GET /companies/{kvk_number}/jobs-history`

History of jobs scrapes, newest first.

Responses:

- `200 OK` — `JobsScrapeRead[]`. Empty array when the company exists but has
  never had jobs scraped.
- `404 Not Found` — no company with that KVK number.

### `POST /companies/{kvk_number}/geocode`

Geocodes every address on the company via the Dutch government's PDOK
Locatieserver (free, keyless, BAG-backed). Only street-address-level
matches (`type=adres`) are accepted — postcode or street centroids are
ignored. Each address's `lat`, `lon`, and `geocoded_at` fields are
updated; addresses that PDOK can't resolve keep their existing `lat`/`lon`
but still have `geocoded_at` stamped.

Path parameters:

| Name         | Type   | Description           |
|--------------|--------|-----------------------|
| `kvk_number` | string | KVK registration nr.  |

Responses:

- `200 OK` — updated `CompanyRead`. Addresses are included with populated
  coordinates where PDOK had a match.
- `404 Not Found` — no company with that KVK number.
- `502 Bad Gateway` — one or more PDOK calls failed with a network-level
  error (timeout, non-200). Any partial successes are still committed.

## Schemas

### `CompanyRead`

| Field        | Type                  |
|--------------|-----------------------|
| `kvk_number` | string                |
| `names`      | `CompanyNameRead[]`   |
| `addresses`  | `AddressRead[]`       |

### `CompanyNameRead`

| Field  | Type                                            |
|--------|-------------------------------------------------|
| `name` | string                                          |
| `type` | enum (`statutory`, `trade`, `short`, `alias`)   |

### `AddressRead`

| Field          | Type                          |
|----------------|-------------------------------|
| `street`       | string \| null                |
| `house_number` | string \| null                |
| `postcode`     | string \| null                |
| `city`         | string \| null                |
| `country`      | string                        |
| `lat`          | decimal \| null               |
| `lon`          | decimal \| null               |
| `geocoded_at`  | datetime \| null (ISO-8601)   |

### `WebsiteSearchDetail`

| Field        | Type                                    |
|--------------|-----------------------------------------|
| `id`         | int                                     |
| `query`      | string (the exact query sent to Serper) |
| `status`     | enum (`success`, `failed`)              |
| `error`      | string \| null                          |
| `results`    | object \| null (raw Serper JSON)        |
| `created_at` | datetime (ISO-8601, tz-aware)           |

### `WebsiteRead`

| Field              | Type                                            |
|--------------------|-------------------------------------------------|
| `id`               | int                                             |
| `source_search_id` | int (FK → the `WebsiteSearch` this was built on)|
| `url`              | string \| null (null = no confident match)      |
| `homepage_url`     | string \| null (`scheme://netloc/` of `url`)    |
| `confidence`       | enum (`high`, `medium`, `low`, `none`)          |
| `reason`           | string (short LLM rationale, or failure code)   |
| `llm_model`        | string (e.g. `claude-haiku-4-5`; empty on skip) |
| `created_at`       | datetime (ISO-8601, tz-aware)                   |

### `WebsiteScrapeRead`

| Field               | Type                                                           |
|---------------------|----------------------------------------------------------------|
| `id`                | int                                                            |
| `source_website_id` | int (FK → the `CompanyWebsite` this scrape targeted)           |
| `status`            | enum (`ok`, `partial`, `failed`, `skipped_no_website`, `skipped_js_heavy`, `skipped_dead_domain`) |
| `pages_attempted`   | int                                                            |
| `pages_ok`          | int                                                            |
| `pages_failed`      | int                                                            |
| `error`             | string \| null (short code, e.g. `dead_domain`, `all_failed`)  |
| `started_at`        | datetime (ISO-8601, tz-aware)                                  |
| `finished_at`       | datetime \| null                                               |
| `created_at`        | datetime (ISO-8601, tz-aware)                                  |
| `pages`             | `WebsitePageRead[]`                                            |

### `WebsitePageRead`

| Field            | Type                                                                   |
|------------------|------------------------------------------------------------------------|
| `id`             | int                                                                    |
| `url`            | string (the URL that was requested)                                    |
| `normalized_url` | string (lowercased host + collapsed trailing slash, deduped per scrape)|
| `fetch_method`   | enum (`http`, `jina`, `firecrawl`, `playwright`)                       |
| `status`         | enum (`ok`, `http_4xx`, `http_5xx`, `timeout`, `network_error`, `js_required`, `blocked`, `dead_domain`, `non_html`) |
| `http_status`    | int \| null                                                            |
| `content_type`   | string \| null                                                         |
| `content_hash`   | string \| null (sha256 hex of the extracted markdown)                  |
| `title`          | string \| null                                                         |
| `markdown`       | string \| null (extracted via trafilatura; null for non-OK pages)      |
| `fetched_at`     | datetime (ISO-8601, tz-aware)                                          |

Raw HTML is persisted to disk under `SCRAPED_HTML_DIR` (default
`data/scraped_html/`) at `{company_id}/{scrape_id}/{page_id}.html`. The
on-disk path is an internal detail and is not exposed on `WebsitePageRead`.

### `CompanyCareersUrlRead`

| Field              | Type                                                      |
|--------------------|-----------------------------------------------------------|
| `id`               | int                                                       |
| `source_scrape_id` | int (FK → the `WebsiteScrape` this was built on)          |
| `url`              | string \| null (null = no same-domain careers page found) |
| `confidence`       | enum (`high`, `medium`, `low`, `none`)                    |
| `reason`           | string (short LLM rationale, or error code)               |
| `llm_model`        | string (e.g. `claude-haiku-4-5`; empty when not called)   |
| `created_at`       | datetime (ISO-8601, tz-aware)                             |

### `JobsScrapeRead`

| Field                | Type                                                       |
|----------------------|------------------------------------------------------------|
| `id`                 | int                                                        |
| `source_careers_id`  | int (FK → the `CompanyCareersUrl` this scrape targeted)    |
| `fetched_url`        | string (the URL actually fetched)                          |
| `status`             | enum (`ok`, `no_jobs`, `no_careers_page`, `js_required`, `blocked`, `failed`, `llm_error`) |
| `http_status`        | int \| null                                                |
| `content_hash`       | string \| null (sha256 of the markdown used for extraction)|
| `llm_model`          | string \| null                                             |
| `error`              | string \| null                                             |
| `started_at`         | datetime (ISO-8601, tz-aware)                              |
| `finished_at`        | datetime \| null                                           |
| `created_at`         | datetime (ISO-8601, tz-aware)                              |
| `jobs`               | `JobRead[]`                                                |

Careers-page HTML is persisted to disk under `SCRAPED_HTML_DIR` at
`{company_id}/jobs/{jobs_scrape_id}.html`. Not exposed on `JobsScrapeRead`.

### `JobRead`

| Field             | Type                                                                   |
|-------------------|------------------------------------------------------------------------|
| `id`              | int                                                                    |
| `title`           | string                                                                 |
| `url`             | string \| null (per-posting detail URL when visible in the listing)    |
| `location`        | string \| null                                                         |
| `employment_type` | enum (`full_time`, `part_time`, `contract`, `internship`, `unknown`)   |
| `department`      | string \| null                                                         |
| `raw_snippet`     | string \| null (verbatim markdown fragment used at extraction, ≤ 400 chars) |
| `created_at`      | datetime (ISO-8601, tz-aware)                                          |
