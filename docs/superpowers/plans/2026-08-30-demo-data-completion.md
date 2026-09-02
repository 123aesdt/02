# Demo Data Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill the three approved demo surfaces with clearly attributed virtual data while preserving real-data priority.

**Architecture:** Add one immutable frontend demo-snapshot catalog and small pure selectors. Pages consume those selectors only when local demo authentication is active; live API values and real task IDs suppress the relevant fallback.

**Tech Stack:** React, TypeScript, Vitest, React DOM test utilities, Vite.

**Spec:** `docs/superpowers/specs/2026-08-30-demo-data-completion-design.md`

## Global Constraints

- Do not add or log secrets.
- Do not write demo values to backend persistence or messaging systems.
- Real API and WebSocket values always take priority.
- Every virtual value is labeled “演示数据” or “混合数据”.
- Do not commit; the user explicitly requested no Git commit.

---

### Task 1: Shared demo snapshot policy and catalog

**Files:**
- Create: `frontend/src/demo/demo-snapshots.ts`
- Test: `frontend/tests/demo-snapshots.test.ts`

**Interfaces:**
- Produces: `isDemoSnapshotEnabled(config)`, `demoCapabilitySummaries`, `demoAgentSnapshots`, `demoObservabilityMetrics`, and `mergeObservabilityMetrics(live, enabled)`.
- Consumers: all three page tasks below.

- [ ] **Step 1: Write the failing policy and merge tests**

```ts
expect(isDemoSnapshotEnabled({ dataMode: "api", authenticationMode: "development_jwt" })).toBe(true);
expect(isDemoSnapshotEnabled({ dataMode: "api", authenticationMode: "oidc_jwt" })).toBe(false);
expect(mergeObservabilityMetrics({ http_qps: 9 }, true).metrics.http_qps).toBe(9);
expect(mergeObservabilityMetrics({ http_qps: 9 }, true).demoKeys).toContain("agent_p95");
```

- [ ] **Step 2: Run the test and verify it fails because the module does not exist**

Run: `npm test -- demo-snapshots.test.ts`

- [ ] **Step 3: Implement immutable demo records and a live-first merge**

```ts
export function isDemoSnapshotEnabled(config: DemoRuntimeConfig) {
  return config.dataMode === "mock" || config.authenticationMode === "development_jwt";
}
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `npm test -- demo-snapshots.test.ts`

### Task 2: Complete the system overview capability cards

**Files:**
- Modify: `frontend/src/pages/admin-overview-page.tsx`
- Test: `frontend/tests/admin-workspace.test.tsx`

**Interfaces:**
- Consumes: `isDemoSnapshotEnabled`, `demoCapabilitySummaries`.
- Produces: live count cards plus four explicitly labeled demo summaries in local demo auth only.

- [ ] **Step 1: Change the existing capability-source test to require four demo badges and no unlabelled fallback**

```ts
expect(badges.filter((badge) => badge.textContent?.includes("演示数据"))).toHaveLength(4);
expect(view.container.textContent).toContain("实时计数与演示摘要");
```

- [ ] **Step 2: Run `npm test -- admin-workspace.test.tsx` and verify the old “待独立数据源” behavior fails**

- [ ] **Step 3: Render catalog summaries only when the shared demo policy is enabled**

- [ ] **Step 4: Rerun the focused test and verify it passes**

### Task 3: Provide an eight-agent demo execution when no real task is selected

**Files:**
- Modify: `frontend/src/pages/agents-page.tsx`
- Create: `frontend/tests/agents-demo-fallback.test.tsx`

**Interfaces:**
- Consumes: `isDemoSnapshotEnabled`, `demoAgentSnapshots`.
- Produces: `DEMO-TASK-001` presentation for local demo auth and immediate live-mode handoff after task ID input.

- [ ] **Step 1: Write a component test for default demo rendering and real task-ID suppression**

```ts
expect(container.textContent).toContain("DEMO-TASK-001");
expect(container.textContent).toContain("演示数据");
await typeTaskId("TASK-LIVE-9");
expect(container.textContent).not.toContain("DEMO-TASK-001");
expect(container.textContent).toContain("等待真实任务事件");
```

- [ ] **Step 2: Run the focused test and verify the API page currently shows “等待任务 ID”**

- [ ] **Step 3: Derive `showDemoSnapshot` during render and keep real event selection unchanged**

- [ ] **Step 4: Rerun the focused test and verify it passes**

### Task 4: Fill only missing operations telemetry

**Files:**
- Modify: `frontend/src/components/live-observability-panel.tsx`
- Modify: `frontend/src/pages/operations-page.tsx`
- Test: `frontend/tests/monitoring-live.test.tsx`
- Test: `frontend/tests/operator-workspace.test.tsx`

**Interfaces:**
- Consumes: `mergeObservabilityMetrics`, `isDemoSnapshotEnabled`.
- Produces: per-metric demo labels, a mixed-data notice, and unchanged live dependency health.

- [ ] **Step 1: Write tests proving live `http_qps` wins, missing `agent_p95` is filled, and the monitor page without opt-in stays unchanged**

```ts
expect(container.textContent).toContain("12.50");
expect(container.textContent).toContain("智能体 P95");
expect(container.textContent).toContain("演示");
```

- [ ] **Step 2: Run the two focused tests and verify missing telemetry still renders `—`**

- [ ] **Step 3: Add an explicit `demoFallback` prop and enable it only from the local-demo operations page**

- [ ] **Step 4: Rerun both focused tests and verify they pass**

### Task 5: Regression and quality gates

**Files:**
- Inspect: all modified files and the repository diff.

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: verified working frontend without a Git commit.

- [ ] **Step 1: Run all targeted tests**

Run: `npm test -- demo-snapshots.test.ts admin-workspace.test.tsx agents-demo-fallback.test.tsx monitoring-live.test.tsx operator-workspace.test.tsx`

- [ ] **Step 2: Run the full frontend suite, lint, and production build**

Run: `npm test`

Run: `npm run lint`

Run: `npm run build`

- [ ] **Step 3: Inspect the final diff and whitespace**

Run: `git -c safe.directory=<workspace> diff --check`

Run: `git -c safe.directory=<workspace> diff -- frontend docs/superpowers`

