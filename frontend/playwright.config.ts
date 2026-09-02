import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["json", { outputFile: process.env.E2E_JSON_REPORT ?? "../docs/verification/raw/v2-d2-browser-e2e.json" }]],
  use: {
    baseURL: process.env.E2E_WEB_BASE_URL ?? "http://localhost:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
  },
  expect: { timeout: 15_000 },
  timeout: 60_000,
});
