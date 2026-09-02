import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuditWorkspace } from "../src/pages/audit-page";
import { createSecurityAuditClient, SecurityAuditApiError } from "../src/services/api/security-audit-client";
import type { SecurityAuditEvent } from "../src/services/api/security-audit-client";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const event: SecurityAuditEvent = {
  event_id: "audit-001",
  event_type: "RUNTIME_OVERRIDE_DENIED",
  subject_id: "supervisor-01",
  permission: "runtime:override",
  route_template: "/api/v1/runtime/tasks/{task_id}/override",
  status: "DENIED",
  reason_code: "PERMISSION_DENIED",
  request_id: "request-001",
  remote_ip: "127.0.0.1",
  created_at: "2026-08-29T08:00:00+08:00",
};

async function renderWorkspace() {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<AuditWorkspace state={{ state: "READY", data: [event] }} />);
  });
  return { container, root };
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("Auditor workspace", () => {
  it("test_auditor_read_only", async () => {
    const view = await renderWorkspace();
    expect(view.container.querySelector("h1")?.textContent).toBe("审计中心");
    expect(view.container.textContent).toContain("RUNTIME_OVERRIDE_DENIED");
    expect(view.container.textContent).toContain("PERMISSION_DENIED");
    expect(view.container.textContent).toContain("supervisor-01");
    expect(view.container.textContent).toContain("只读");
    expect(view.container.textContent).toContain("未开放");
  });

  it("test_auditor_no_write_action", async () => {
    const view = await renderWorkspace();
    expect(view.container.querySelectorAll("button")).toHaveLength(0);
    expect(view.container.textContent).not.toMatch(/确认|拒绝|修改|覆盖|重试|发起/);
  });

  it("shows manual review decisions in Chinese while preserving the stable API enum", async () => {
    const reviewEvent: SecurityAuditEvent = {
      ...event,
      event_id: "audit-review-001",
      event_type: "REVIEW_DECISION",
      permission: "dispatch:review",
      reason_code: "REVIEW_REJECTED",
    };
    const container = document.createElement("div");
    document.body.append(container);
    const root = createRoot(container);

    await act(async () => { root.render(<AuditWorkspace state={{ state: "READY", data: [reviewEvent] }} />); });

    expect(container.textContent).toContain("人工复核决定");
    expect(container.textContent).toContain("人工复核已拒绝");
    expect(container.textContent).not.toContain("REVIEW_DECISION");
    expect(container.textContent).not.toContain("REVIEW_REJECTED");
  });
});

describe("Security audit client", () => {
  it("reads only the published audit projection", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ items: [event] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    const client = createSecurityAuditClient({ baseUrl: "http://api.example", fetchImpl: fetchImpl as typeof fetch });
    await expect(client.listRecent()).resolves.toEqual([event]);
    expect(fetchImpl).toHaveBeenCalledWith("http://api.example/api/v1/security/audit?limit=100", expect.objectContaining({ headers: expect.any(Headers) }));
  });

  it("maps permission failures without fabricating events", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ detail: { code: "PERMISSION_DENIED" } }), { status: 403 }));
    const client = createSecurityAuditClient({ baseUrl: "http://api.example", fetchImpl: fetchImpl as typeof fetch });
    await expect(client.listRecent()).rejects.toMatchObject({ status: 403 } satisfies Partial<SecurityAuditApiError>);
  });
});
