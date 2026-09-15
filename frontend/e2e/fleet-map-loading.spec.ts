import { expect, test } from "@playwright/test";

import { authenticatePage } from "./support/security-auth";

test("fleet navigation never mounts the legacy map while AMap and vehicles load", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await authenticatePage(page, "ADMIN", "/overview");
  await page.evaluate(() => {
    const state = window as typeof window & { __fleetLegacyMapMounts?: number; __fleetMapObserver?: MutationObserver };
    state.__fleetLegacyMapMounts = 0;
    state.__fleetMapObserver = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (!(node instanceof Element)) continue;
          if (node.matches(".fleet-sandbox-canvas") || node.querySelector(".fleet-sandbox-canvas")) {
            state.__fleetLegacyMapMounts = (state.__fleetLegacyMapMounts ?? 0) + 1;
          }
        }
      }
    });
    state.__fleetMapObserver.observe(document.body, { childList: true, subtree: true });
  });

  await page.getByRole("link", { name: "车辆态势地图" }).click();
  await expect(page).toHaveURL(/\/fleet-live-map$/);

  const stage = page.locator(".fleet-amap-stage");
  await expect(stage).toHaveCount(1);
  await expect(page.locator(".fleet-sandbox-canvas")).toHaveCount(0);
  await expect(stage).toHaveAttribute("data-amap-state", "READY", { timeout: 20_000 });
  await expect(stage).toHaveAttribute("data-road-planned-count", "10", { timeout: 20_000 });
  await expect(page.locator(".amap-fleet-vehicle")).toHaveCount(20);
  await expect.poll(() => page.evaluate(() => (
    (window as typeof window & { __fleetLegacyMapMounts?: number }).__fleetLegacyMapMounts ?? 0
  ))).toBe(0);
});
