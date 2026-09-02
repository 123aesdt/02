import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const screenshotDirectory = path.resolve(import.meta.dirname, "../../docs/verification/v2-g1/screenshots");

test("capture real observability failure and Grafana evidence", async ({ page }) => {
  fs.mkdirSync(screenshotDirectory, { recursive: true });
  const mode = process.env.E2E_OBSERVABILITY_SCREENSHOT_MODE;
  if (mode === "neo4j-down") {
    await page.goto("/monitor");
    await expect(page.getByText("Neo4j DOWN")).toBeVisible({ timeout: 45_000 });
    await page.screenshot({ path: path.join(screenshotDirectory, "dependency-down.png"), fullPage: true });

    await page.goto("http://localhost:3000/login");
    const user = process.env.GRAFANA_ADMIN_USER;
    const password = process.env.GRAFANA_ADMIN_PASSWORD;
    if (!user || !password) throw new Error("Grafana credentials are required but never recorded");
    if (page.url().includes("/login")) {
      await page.getByRole("textbox", { name: "Email or username" }).fill(user);
      await page.getByRole("textbox", { name: "Password" }).fill(password);
      await page.getByRole("button", { name: /log in/i }).click();
      await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 15_000 });
    }
    await page.goto("http://localhost:3000/d/countyflow-v2-operations/countyflow-v2-operations?orgId=1");
    await expect(page.getByText("CountyFlow V2 Operations Overview")).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(2_000);
    await page.screenshot({ path: path.join(screenshotDirectory, "grafana-slo-overview.png"), fullPage: true });
    await page.screenshot({ path: path.join(screenshotDirectory, "grafana-agents.png"), fullPage: true });
    await page.screenshot({ path: path.join(screenshotDirectory, "grafana-memory-runtime.png"), fullPage: true });
    return;
  }
  if (mode === "prometheus-down") {
    await page.goto("/monitor");
    await expect(page.getByText("Monitoring unavailable", { exact: true })).toBeVisible({ timeout: 30_000 });
    await page.screenshot({ path: path.join(screenshotDirectory, "prometheus-unavailable.png"), fullPage: true });
    return;
  }
  throw new Error("Unknown screenshot mode");
});
