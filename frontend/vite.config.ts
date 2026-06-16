import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev-only frontend. Every API route lives under /companies, so a single
// proxy makes the whole API reachable same-origin — no CORS needed on the
// FastAPI side. Start the API on :8000 (uvicorn) before `npm run dev`.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/companies": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
