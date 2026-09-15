import { expect, test } from "@playwright/test";

declare global {
  interface Window {
    __countyLoginPerf?: { layoutShifts: number[]; longTasks: number[] };
  }
}

test("login page remains responsive, quiet, and compositor-friendly", async ({ page }) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const backgroundRequests: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (request) => {
    if (request.url().includes("county-valley-logistics-sunrise.png")) backgroundRequests.push(request.url());
  });
  await page.addInitScript(() => {
    window.__countyLoginPerf = { layoutShifts: [], longTasks: [] };
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const shift = entry as PerformanceEntry & { value?: number; hadRecentInput?: boolean };
        if (!shift.hadRecentInput) window.__countyLoginPerf?.layoutShifts.push(shift.value ?? 0);
      }
    }).observe({ type: "layout-shift", buffered: true });
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) window.__countyLoginPerf?.longTasks.push(entry.duration);
    }).observe({ type: "longtask", buffered: true });
  });

  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await expect(page.locator("[data-county-login]")).toBeVisible();
  await expect(page.locator("[data-login-vehicle]")).toBeVisible();
  await expect(page.getByRole("heading", { name: "县域物流 智慧配送平台" })).toBeVisible();
  await page.waitForTimeout(1_500);
  await page.mouse.move(1420, 340);
  await expect.poll(() => page.locator("[data-county-login]").evaluate((node) => (
    getComputedStyle(node).getPropertyValue("--login-parallax-x").trim()
  ))).not.toBe("0");

  const performance = await page.evaluate(async () => {
    const frameTimes: number[] = [];
    await new Promise<void>((resolve) => {
      const tick = (time: number) => {
        frameTimes.push(time);
        if (frameTimes.length >= 90) resolve();
        else requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    const intervals = frameTimes.slice(1).map((time, index) => time - frameTimes[index]);
    const sortedIntervals = [...intervals].sort((left, right) => left - right);
    const refreshFrameMs = sortedIntervals[Math.floor(sortedIntervals.length / 2)];
    const resources = performance.getEntriesByType("resource") as PerformanceResourceTiming[];
    return {
      averageFrameMs: intervals.reduce((sum, value) => sum + value, 0) / intervals.length,
      refreshFrameMs,
      maxFrameMs: Math.max(...intervals),
      droppedFrames: intervals.filter((value) => value > refreshFrameMs * 1.8).length,
      layoutShift: window.__countyLoginPerf?.layoutShifts.reduce((sum, value) => sum + value, 0) ?? 0,
      longTasks: window.__countyLoginPerf?.longTasks ?? [],
      backgroundEntries: resources.filter((entry) => entry.name.includes("county-valley-logistics-sunrise.png")).length,
    };
  });
  console.log(`LOGIN_PERF ${JSON.stringify(performance)}`);
  expect(performance.backgroundEntries).toBe(1);
  expect(backgroundRequests).toHaveLength(1);
  expect(performance.layoutShift).toBeLessThan(.1);
  expect(performance.droppedFrames).toBeLessThanOrEqual(2);
  expect(performance.longTasks.filter((duration) => duration > 100)).toHaveLength(0);
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
  await page.screenshot({ path: "../.tmp/login-desktop-1920.png", fullPage: true });

  await page.setViewportSize({ width: 1366, height: 768 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight)).toBeLessThanOrEqual(1);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
  await page.screenshot({ path: "../.tmp/login-desktop-1366.png", fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".county-login__capabilities")).toBeHidden();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight)).toBeLessThanOrEqual(1);
  await page.screenshot({ path: "../.tmp/login-mobile-390.png", fullPage: true });
});

test("login page respects reduced motion", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.locator("[data-county-login]")).toBeVisible();
  await expect(page.locator(".county-login__scene img")).toHaveCSS("animation-name", "none");
  await expect(page.locator("[data-login-vehicle] > div")).toHaveCSS("animation-name", "none");
  await expect(page.locator("[data-login-particle]").first()).toBeHidden();
});
