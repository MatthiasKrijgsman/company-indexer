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

- `200 OK` — `WebsiteSearchRead` (see below).
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

| Field          | Type             |
|----------------|------------------|
| `street`       | string \| null   |
| `house_number` | string \| null   |
| `postcode`     | string \| null   |
| `city`         | string \| null   |
| `country`      | string           |
| `lat`          | decimal \| null  |
| `lon`          | decimal \| null  |

### `WebsiteSearchRead`

| Field        | Type                           |
|--------------|--------------------------------|
| `id`         | int                            |
| `status`     | enum (`success`, `failed`)     |
| `created_at` | datetime (ISO-8601, tz-aware)  |

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
| `confidence`       | enum (`high`, `medium`, `low`, `none`)          |
| `reason`           | string (short LLM rationale, or failure code)   |
| `llm_model`        | string (e.g. `claude-haiku-4-5`; empty on skip) |
| `created_at`       | datetime (ISO-8601, tz-aware)                   |
