import { expect, type Page } from "@playwright/test";

export async function openOverrideDialog(page: Page, taskId: string, target: "BROKEN" | "UNAVAILABLE" | "MAINTENANCE") {
  const targetPath = `/dispatch/${encodeURIComponent(taskId)}`;
  if (new URL(page.url()).pathname !== targetPath) await page.goto(targetPath);
  const panel = page.getByTestId("runtime-intervention");
  await expect(panel).toContainText("可干预");
  await panel.locator(`button[data-target="${target}"]`).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  return dialog;
}

export async function confirmOverride(page: Page, reason = "人工确认车辆爆胎") {
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("干预原因").fill(reason);
  await dialog.getByRole("button", { name: "确认干预" }).click();
}
