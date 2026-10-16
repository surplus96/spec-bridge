// Dev server and build for the review UI (W5-5, D-061).
// Dev: `npm run dev` on 127.0.0.1:5173, API calls proxied to the FastAPI server on :8000.
// Build: `npm run build` → dist/, which FastAPI serves on the same origin (no CORS, no CDN).
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const api = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": api, "/health": api },
  },
  // pdf.js (PdfView chunk) is ~630 kB and loads only when a PDF job is opened.
  build: { outDir: "dist", chunkSizeWarningLimit: 700 },
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"] },
});
