import crypto from "node:crypto";

import type { Page } from "@playwright/test";

export type SecurityRole = "EMPLOYEE" | "DISPATCHER" | "SUPERVISOR" | "OPERATOR" | "AUDITOR" | "ADMIN";

const demoEmployeeByRole: Record<SecurityRole, { employeeId: string; displayName: string }> = {
  EMPLOYEE: { employeeId: "CF-DEMO-001", displayName: "张师傅" },
  DISPATCHER: { employeeId: "CF-DEMO-007", displayName: "孙调度" },
  OPERATOR: { employeeId: "CF-DEMO-002", displayName: "李运营" },
  SUPERVISOR: { employeeId: "CF-DEMO-003", displayName: "王主管" },
  AUDITOR: { employeeId: "CF-DEMO-004", displayName: "赵审计" },
  ADMIN: { employeeId: "CF-DEMO-005", displayName: "系统管理员" },
};

function base64url(value: string): string {
  return Buffer.from(value).toString("base64url");
}

export function developmentToken(role: SecurityRole, ttlSeconds = 600): string {
  const secret = process.env.DEVELOPMENT_JWT_SECRET;
  if (!secret || secret.length < 32) throw new Error("DEVELOPMENT_JWT_SECRET is required for security browser E2E");
  const now = Math.floor(Date.now() / 1000);
  const header = base64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = base64url(JSON.stringify({
    iss: process.env.AUTH_ISSUER ?? "countyflow-dev",
    aud: process.env.AUTH_AUDIENCE ?? "countyflow-api",
    sub: `e2e-${role.toLowerCase()}`,
    name: `E2E ${role}`,
    roles: [role],
    iat: now,
    nbf: now,
    exp: now + ttlSeconds,
    jti: crypto.randomUUID(),
  }));
  const signature = crypto.createHmac("sha256", secret).update(`${header}.${payload}`).digest("base64url");
  return `${header}.${payload}.${signature}`;
}

export async function authenticatePage(page: Page, role: SecurityRole, path = "/"): Promise<string> {
  const employee = demoEmployeeByRole[role];
  await page.goto("/");
  const sessionResponse = page.waitForResponse((response) => (
    response.url().endsWith("/api/v1/auth/demo-session")
    && response.request().method() === "POST"
  ));
  await page.getByRole("combobox", { name: "切换演示员工" }).selectOption(employee.employeeId);
  const response = await sessionResponse;
  if (!response.ok()) throw new Error(`Demo employee session failed with ${response.status()}`);
  const payload = await response.json() as { access_token: string };
  await page.locator(".auth-session-banner").filter({ hasText: employee.displayName }).waitFor();
  if (path !== "/") {
    await page.evaluate((targetPath) => {
      window.history.pushState(null, "", targetPath);
      window.dispatchEvent(new PopStateEvent("popstate"));
    }, path);
  }
  if (await page.locator('input[type="password"]').count()) throw new Error("Manual token login must remain removed");
  return payload.access_token;
}

export function bearer(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}
