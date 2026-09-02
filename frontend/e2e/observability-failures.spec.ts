import { expect, test } from "@playwright/test";

test("API mode renders Monitoring unavailable and never demo data", async ({ page }) => {
  await page.route("**/api/v1/observability/**", (route) => route.fulfill({ status: 503, contentType: "application/json", body: '{"code":"OBSERVABILITY_UNAVAILABLE"}' }));
  await page.goto("/monitor");
  await expect(page.getByText("Monitoring unavailable", { exact: true })).toBeVisible();
  await expect(page.getByText("DEMO DATA", { exact: true })).toHaveCount(0);
});

test("monitor:read denial is explicit", async ({ page }) => {
  await page.route("**/api/v1/observability/**", (route) => route.fulfill({ status: 403, contentType: "application/json", body: '{"code":"OBSERVABILITY_FORBIDDEN"}' }));
  await page.goto("/monitor");
  await expect(page.getByText("Monitoring permission required", { exact: true })).toBeVisible();
});
