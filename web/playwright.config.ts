import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E configuration for A-Cal.
 *
 * Starts both the Python backend (port 8000) and the Next.js frontend
 * (port 3456) before running tests. The frontend proxies /api/* to the
 * backend via next.config.mjs rewrites.
 *
 * The frontend uses `next start` (production build) for reliable hydration.
 * Run `pnpm build` before the first test run, or use `pnpm test:e2e` which
 * builds automatically.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: "list",
  timeout: 30_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL: "http://localhost:3456",
    trace: "on-first-retry",
    headless: true,
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: [
    {
      command: `cd .. && ${process.env.CI ? "python" : ".venv/bin/python"} -m a_cal.api.standalone`,
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: true,
      timeout: 30_000,
      stdout: "ignore",
      stderr: "pipe",
    },
    {
      command: "npx next start --port 3456",
      url: "http://localhost:3456",
      reuseExistingServer: true,
      timeout: 30_000,
      stdout: "ignore",
      stderr: "pipe",
    },
  ],
});
