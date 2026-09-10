import { expect, test } from "@playwright/test";

import { apiBaseUrl, createRuntimeTask } from "./support/api";
import { authenticatePage, bearer, developmentToken } from "./support/security-auth";

test("test_browser_runtime_override_forbidden", async ({ page, request }) => {
  const taskId = await createRuntimeTask(request);
  await authenticatePage(page, "DISPATCHER", `/dispatch/${taskId}`);
  await expect(page.getByRole("heading", { name: "运行态不可用" })).toBeVisible();
  await expect(page.getByText("当前身份缺少 runtime:read 权限。")).toBeVisible();
  await expect(page.locator('button[data-target="BROKEN"]')).toHaveCount(0);
  const response = await request.post(`${apiBaseUrl}/api/v1/runtime/threads/${encodeURIComponent(`cf:dispatch:${taskId}`)}/overrides`, { headers: bearer(developmentToken("DISPATCHER")), data: {
    idempotency_key: `runtime-override:${crypto.randomUUID()}`, entity_type: "Vehicle", entity_id: "vehicle-001", field: "status",
    old_value: "NORMAL", new_value: "BROKEN", reason: "人工确认车辆爆胎", expected_version: 0, expected_next_node: "capacity",
  } });
  expect(response.status()).toBe(403); expect((await response.json()).code).toBe("AUTHORIZATION_DENIED");
});
