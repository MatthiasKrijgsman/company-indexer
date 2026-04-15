# MVP Plan — company-indexer

A minimal first slice: stand up Postgres + Redis, define the core company/name/address models, seed some data manually, and expose read-only API endpoints. No enrichment, no worker, no auth. The goal is a working queryable warehouse in as little code as possible — everything else in `initial-plan.md` is a follow-up slice.

Redis is included in infra from day one even though it's not used yet, so slice 2 (queue + worker) doesn't need to touch compose.

## Scope

**In:**
- `docker-compose.yml` with Postgres and Redis.
- Python project skeleton (`pyproject.toml`, `.env.example`, updated `.gitignore`, short `README.md`).
- SQLAlchemy models: `Company`, `CompanyName` (+ `NameType` enum), `Address`.
- Schema created directly from the models via `Base.metadata.create_all` on startup (no Alembic yet).
- Seed script to manually insert a handful of companies.
- FastAPI app with two read endpoints.

**Out (deferred to later slices):**
- Alembic / migrations — will be added once the schema stabilizes and we have data worth preserving across changes. For now, iterate freely and drop/recreate the DB when models change.
- RQ, worker process, enrichment package.
- `POST /companies/{kvk}/enrich`.
- KVK scraper.
- API tokens, call logging, billing.
- Dockerfiles for the API itself (run on the host against compose for now).
- Tests beyond a smoke test, if any.

## Folder structure (MVP only)

```
company-indexer/
├── docker-compose.yml
├── pyproject.toml
├── .env.example
├── .gitignore
├── README.md
└── src/
    └── company_indexer/
        ├── __init__.py
        ├── config.py              # pydantic-settings, reads .env
        ├── db.py                  # async engine + session factory
        ├── models/
        │   ├── __init__.py
        │   └── company.py         # Company, CompanyName, NameType, Address
        ├── schemas/
        │   ├── __init__.py
        │   └── company.py         # CompanyRead, CompanyNameRead, AddressRead
        ├── api/
        │   ├── __init__.py
        │   ├── app.py             # FastAPI app factory
        │   ├── deps.py            # get_session dep
        │   └── routes/
        │       ├── __init__.py
        │       └── companies.py   # GET /companies, GET /companies/{kvk}
        └── scripts/
            ├── __init__.py
            └── seed_companies.py
```

## Infrastructure — `docker-compose.yml`

- `postgres:16` on `5432`, named volume for persistence, env-configured DB/user/password.
- `redis:7` on `6379`. Included now so it's there when slice 2 adds the worker; MVP code doesn't connect to it yet.

Both bound to `localhost` only. API runs on the host via `uvicorn` for fast iteration.

## Data model

- **Company** — `id` (PK, surrogate), `kvk_number` (unique, indexed — external identifier), `created_at`, `updated_at`.
- **CompanyName** — `id`, `company_id` (FK, cascade delete), `name`, `type` (`NameType` enum), `created_at`. Index on `company_id`; partial unique index on `(company_id, type)` for `statutory` so there's only one legal name per company.
- **NameType** — native Postgres enum: `statutory`, `trade`, `short`, `alias`.
- **Address** — `id`, `company_id` (FK, cascade delete), `street`, `house_number`, `postcode`, `city`, `country` (default `NL`), `lat` (nullable), `lon` (nullable), `created_at`. `lat`/`lon` stay null in the MVP — they get populated later by the geocode enricher.

Schema is created from the models via `Base.metadata.create_all` — called once at app startup and also at the top of the seed script. The Postgres enum for `NameType` is created by SQLAlchemy as part of that. When you change a model during MVP iteration, the workflow is: `docker compose down -v` (or drop the DB) and start fresh. Alembic gets introduced later, before real data matters.

## API endpoints

Both read-only, JSON, no auth.

### `GET /companies`

Lists companies. Supports:
- `?limit=` (default 50, max 200)
- `?offset=` (default 0)
- `?q=` (optional substring match against `CompanyName.name`, case-insensitive)

Response shape:
```json
{
  "items": [
    {
      "kvk_number": "12345678",
      "names": [
        {"name": "Acme Holding B.V.", "type": "statutory"},
        {"name": "Acme", "type": "trade"}
      ],
      "addresses": [
        {
          "street": "Damrak", "house_number": "1",
          "postcode": "1012LG", "city": "Amsterdam", "country": "NL",
          "lat": null, "lon": null
        }
      ]
    }
  ],
  "limit": 50,
  "offset": 0
}
```

### `GET /companies/{kvk}`

Looks up a single company by `kvk_number`. Returns the same shape as one `items` entry above, or `404` if not found.

Both endpoints eager-load names and addresses (`selectinload`) so there's no N+1.

## Environment variables (`.env.example`)

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/company_indexer
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=INFO
```

## Dependencies (`pyproject.toml`)

Runtime:
- `fastapi`
- `uvicorn[standard]`
- `sqlalchemy>=2`
- `asyncpg`
- `pydantic-settings`
- `redis` (not used yet — reserve the dep so slice 2 is a smaller diff; optional, could defer)

Dev:
- `ruff`
- `pytest` (only if we write any tests in this slice)

## Implementation order

1. `pyproject.toml`, `.env.example`, updated `.gitignore`, `README.md` with "how to run locally".
2. `docker-compose.yml`; `docker compose up -d` and confirm psql + redis-cli connect.
3. `config.py` (settings from env) and `db.py` (async engine + session factory).
4. Models in `models/company.py` with the `NameType` enum.
5. `seed_companies.py` — calls `create_all` then inserts 2–3 realistic companies, each with at least one statutory name, one trade name, and one address. Idempotent (`INSERT ... ON CONFLICT DO NOTHING` on `kvk_number`).
6. Pydantic response schemas in `schemas/company.py`.
7. FastAPI app + `GET /companies` and `GET /companies/{kvk}`. App startup also calls `create_all` so the first `uvicorn` run against a fresh DB just works.
8. Smoke-test manually: run seed, curl both endpoints, delete the old `main.py`.

Rough size target: a few hundred lines total across all files. If any step balloons, it's probably drifting into slice-2 territory.

## What comes next (slice 2 preview)

Once the MVP runs end-to-end, the natural next slice is: add `EnrichmentJob` / `EnrichmentResult` models, the `enrichment/` package with a no-op `Enricher`, the RQ queue wiring, a worker entrypoint, and `POST /companies/{kvk}/enrich`. Real enrichers (geocode, serper, fetch, LLM) come after that, one at a time.
