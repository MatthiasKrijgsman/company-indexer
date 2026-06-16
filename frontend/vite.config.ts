import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev-only frontend. The API routes used by the console live under /companies
// and /pricing, so proxying those makes the whole API reachable same-origin —
// no CORS needed on the FastAPI side. Start the API on :8000 (uvicorn) before
// `npm run dev`.
const API_TARGET = "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/companies": { target: API_TARGET, changeOrigin: true },
      "/pricing": { target: API_TARGET, changeOrigin: true },
    },
  },
});
