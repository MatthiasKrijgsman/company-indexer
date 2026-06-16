# company-indexer — dev frontend

A **development-only** web console for driving and inspecting the company-indexer
API by hand: browse companies and run the enrichment chain (website search →
resolve website → scrape → resolve careers → scrape jobs → geocode) from the
browser instead of curl.

Not for production — no auth, no deploy, no tests.

## Stack

- React 19 + Vite 6 + TypeScript
- Tailwind CSS v4 (`@tailwindcss/vite`)
- [@tanstack/react-query](https://tanstack.com/query) for the data layer
- [`@matthiaskrijgsman/mat-ui`](https://www.npmjs.com/package/@matthiaskrijgsman/mat-ui)
  for components
- `react-router-dom` for the two routes (`/`, `/companies/:kvk`)

## Prerequisites

- Node 20+ (React 19 / Vite + Tailwind v4)
- The API running locally on `http://localhost:8000` (see the repo root
  `README.md`). The Vite dev server proxies `/companies` → `:8000`, so **no CORS
  config is needed** on the backend.

## Run

```bash
# from the repo root, first bring up the API:
#   docker compose up -d
#   python -m company_indexer.scripts.seed_companies
#   uvicorn company_indexer.api.app:app --reload

cd frontend
npm install
npm run dev          # http://localhost:5173
```

Other scripts: `npm run build` (type-check + production bundle),
`npm run preview` (serve the built bundle).

## Layout

```
src/
├── main.tsx            React root: QueryClientProvider + BrowserRouter
├── App.tsx             Header + routes
├── index.css           Tailwind + mat-ui stylesheet imports
├── api/
│   ├── types.ts        Hand-written types mirroring the API schemas
│   ├── client.ts       fetch wrapper + ApiError
│   └── hooks.ts        react-query query + mutation hooks
├── components/         StatusBadge, Section/ErrorNote/NotRunYet
├── pages/
│   ├── CompaniesPage.tsx   List + search
│   ├── CompanyPage.tsx     Detail + enrichment cockpit
│   └── sections.tsx        One component per enrichment step
└── lib/                formatting + useDebounce
```

## Keeping types in sync

`src/api/types.ts` is **hand-maintained** — there is no codegen. When the API
response schemas in `src/company_indexer/schemas/` change (see `VISION.md` §5),
update `types.ts` to match.
