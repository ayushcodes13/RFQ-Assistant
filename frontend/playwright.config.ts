import { defineConfig, devices } from "@playwright/test";
import os from "node:os";
import path from "node:path";

const backendPort = process.env.RFQ_E2E_BACKEND_PORT ?? "8000";
const frontendPort = process.env.RFQ_E2E_FRONTEND_PORT ?? "3000";
const backendUrl = `http://127.0.0.1:${backendPort}`;
const e2eDataDir = process.env.RFQ_E2E_DATA_DIR ?? path.join(os.tmpdir(), `rfq-e2e-${process.pid}`);
const nextDistDir = process.env.RFQ_E2E_NEXT_DIST_DIR ?? ".next-e2e";

/**
 * Full-stack workflow: FastAPI and Next.js use isolated configurable ports.
 * Local runs reuse already-running servers; CI always starts fresh ones.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI
    ? [["github"], ["html", { open: "never" }]]
    : [["list"]],
  use: {
    baseURL: `http://localhost:${frontendPort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: "bash e2e/start-backend.sh",
      url: `${backendUrl}/api/health`,
      reuseExistingServer: !process.env.CI,
      env: {
        RFQ_E2E_BACKEND_PORT: backendPort,
        RFQ_ASSISTANT_STORAGE_DIR: path.join(e2eDataDir, "storage"),
        RFQ_ASSISTANT_DB_PATH: path.join(e2eDataDir, "rfq_assistant.sqlite3"),
        RFQ_ASYNC_INGEST_ENABLED: "true",
      },
      timeout: 120_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: `npm run dev -- --port ${frontendPort}`,
      url: `http://localhost:${frontendPort}`,
      reuseExistingServer: !process.env.CI,
      env: {
        RFQ_ASSISTANT_API_URL: backendUrl,
        RFQ_E2E_NEXT_DIST_DIR: nextDistDir,
      },
      timeout: 180_000,
      stdout: "pipe",
      stderr: "pipe",
    },
  ],
});
