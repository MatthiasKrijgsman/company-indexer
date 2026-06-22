import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev-only frontend. The API routes used by the console live under /companies
// and /pricing, so proxying those makes the whole API reachable same-origin —
// no CORS needed on the FastAPI side. Start the API on :8000 (uvicorn) before
// `npm run dev`.
const API_TARGET = "http://localhost:8000";

// The SPA's client route `/companies/:kvk` collides with the proxied API path.
// On client-side navigation React Router handles it; but on a hard load
// (refresh / pasted URL) the browser fetches `/companies/123` from Vite, which
// would proxy it to FastAPI and return raw JSON. The API client always sends
// `Accept: application/json`, while document navigations send `text/html` — so
// bounce HTML navigations back to index.html and let React Router take over.
const apiProxy = {
  target: API_TARGET,
  changeOrigin: true,
  bypass(req: { headers: { accept?: string } }) {
    if (req.headers.accept?.includes("text/html")) return "/index.html";
  },
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/companies": apiProxy,
      "/pricing": apiProxy,
    },
  },
});
