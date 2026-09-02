import crypto from "node:crypto";
import fs from "node:fs";
import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { apiBaseUrl, e2eHeaders } from "./support/api";

const projectRoot = process.env.E2E_PROJECT_ROOT!;
const docker = process.env.DOCKER_COMMAND!;
const python = process.env.E2E_PYTHON!;
const databaseUrl = process.env.E2E_DATABASE_URL!;

async function qdrant(action: "pause" | "unpause") {
  execFileSync(docker, [action, "countyflow-ai-qdrant-1"], { cwd: projectRoot, stdio: "inherit" });
  if (action === "unpause") {
    await expect.poll(() => {
      try {
        return execFileSync(docker, ["inspect", "countyflow-ai-qdrant-1", "--format", "{{.State.Health.Status}}"], { cwd: projectRoot, encoding: "utf8" }).trim();
      } catch { return "unavailable"; }
    }, { timeout: 30_000, intervals: [250, 500, 1000] }).toBe("healthy");
  }
}

test("test_v2e_real_shared_memory_partial_and_reconcile", async ({ page, request }) => {
  const screenshots = path.resolve(import.meta.dirname, "../../docs/verification/v2-e/screenshots");
  fs.mkdirSync(screenshots, { recursive: true });
  const now = new Date();
  try {
    await qdrant("pause");
    const response = await request.post(`${apiBaseUrl}/api/v1/memory/mutations`, { headers: e2eHeaders(), data: {
      idempotency_key: `v2e-browser-partial-${crypto.randomUUID()}`,
      category: "DispatchMemory", fact_kind: "HYBRID", subject_type: "Vehicle",
      subject_id: `v2e-browser-${crypto.randomUUID()}`, predicate: "STATUS", object_type: "Route",
      object_id: "xinping-road", value_json: { status: "BROKEN" }, expected_version: null,
      confidence: "0.9900", incoming_at: now.toISOString(), expires_at: new Date(now.getTime() + 86_400_000).toISOString(),
      source_type: "v2e_browser", source_id: "partial-reconcile",
      human_confirmed: true, reason: "V2-E browser partial projection", evidence_text: "Qdrant unavailable fault injection",
      evidence_observed_at: now.toISOString(), vector_memory_id: `v2e-browser-memory-${crypto.randomUUID()}`,
      graph_fact_key: `v2e-browser-graph-${crypto.randomUUID()}`, targets: ["VECTOR", "GRAPH"],
    } });
    expect(response.status()).toBe(202);
    const partial = await response.json();
    const mutationId = partial.mutation_id as string;
    await page.setExtraHTTPHeaders(e2eHeaders());
    await page.goto(`${apiBaseUrl}/api/v1/memory/mutations/${mutationId}`);
    await expect(page.locator("body")).toContainText("PARTIAL");
    await expect(page.locator("body")).toContainText("projection_incomplete");
    await page.screenshot({ path: path.join(screenshots, "shared-memory-partial.png"), fullPage: true });
    await qdrant("unpause");
    execFileSync(python, [path.join(projectRoot, "scripts/resume_memory_mutation.py"), "--mutation-id", mutationId, "--database-url", databaseUrl], {
      cwd: projectRoot, stdio: "inherit", env: process.env,
    });
    await page.goto(`${apiBaseUrl}/api/v1/memory/mutations/${mutationId}`);
    await expect(page.locator("body")).toContainText("APPLIED");
    await expect(page.locator("body")).toContainText('"projection_incomplete":false');
    await page.screenshot({ path: path.join(screenshots, "shared-memory-reconciled.png"), fullPage: true });
  } finally {
    try { await qdrant("unpause"); } catch { /* runner also restores */ }
  }
});
