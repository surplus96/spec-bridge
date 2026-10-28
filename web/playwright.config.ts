// Browser end-to-end checks against the real local stack (D-117): the FastAPI app with the
// built UI, the local model server and a fresh app folder. Like the Docling and LLM tests,
// these need local models, so CI does not run them; run `npm run e2e` before a release.
// Port 8011 so a review app already running on 8010 is left alone.
import { defineConfig } from "@playwright/test";

const port = 8011;
const appDir = `var/e2e/run-${Date.now()}`; // a new registry and job list for every run

export default defineConfig({
  testDir: "./e2e",
  testMatch: "*.e2e.ts", // kept apart from the Vitest component tests (*.test.tsx)
  timeout: 6 * 60_000, // the spec-sheet path waits for the local model
  workers: 1,
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
  },
  webServer: {
    command: `cd .. && OFFLINE=1 SPEC_BRIDGE_APP_DIR=${appDir} uv run uvicorn spec_bridge.api.app:app --host 127.0.0.1 --port ${port}`,
    url: `http://127.0.0.1:${port}/`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
