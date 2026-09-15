# CountyFlow Showcase Reliability Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent third-party map failures from replacing the whole application, explain permission redirects, make data provenance unambiguous, and present one consistent vehicle rescue-to-return timeline across dispatcher and employee views.

**Architecture:** Add two independent recovery boundaries: a router-level application error page and a component-level map boundary that remounts AMap or leaves the functional local map visible. Carry permission redirect feedback through router navigation state and render it once in the shared shell. Reuse the existing vehicle-operation snapshot as the single source for shared lifecycle presentation and introduce one provenance badge component for API/demo state.

**Tech Stack:** React, React Router, TypeScript, Vitest, Lucide, existing CountyFlow CSS tokens and vehicle-operation HTTP snapshot.

**Spec:** `docs/superpowers/specs/2026-09-10-vehicle-rescue-maintenance-map-system-design.md`

## Global Constraints

- Keep the existing asynchronous FastAPI → Redis Streams → Worker → MySQL workflow unchanged.
- Never expose or log the AMap key or security code.
- AMap failure must not stop persisted dispatch, rescue, or maintenance processing.
- API mode must never silently replace failed reads with demo data.
- Use behavior-first TDD for every production change.

---

### Task 1: Application and map recovery boundaries

**Files:**

- Create: `frontend/src/components/application-error-page.tsx`
- Create: `frontend/src/components/map-error-boundary.tsx`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/components/fleet-sandbox-map.tsx`
- Modify: `frontend/src/styles/index.css`
- Test: `frontend/tests/error-recovery.test.tsx`

**Interfaces:**

- Produces: `ApplicationErrorPage(): React.ReactNode`, the router `errorElement`.
- Produces: `MapErrorBoundary({ children, onFallback }): React.ReactNode`, which catches provider render/lifecycle failures, keeps the local map available, and remounts children after retry.

- [ ] **Step 1: Write failing behavior tests**

```tsx
it("replaces an unexpected route crash with recoverable CountyFlow actions", async () => {
  // Render a route that throws and assert the shell is replaced by a localized
  // error page containing “重新加载页面” and “返回工作台”.
});

it("contains a map provider crash inside the map surface", async () => {
  // Render MapErrorBoundary with a throwing child and assert the rest of the
  // page stays mounted, the local-map message is visible, and retry remounts.
});
```

- [ ] **Step 2: Run `npm run test -- --run tests/error-recovery.test.tsx` from `frontend` and confirm the missing-component assertions fail.**
- [ ] **Step 3: Implement the two boundaries, wire `errorElement`, and wrap only `AmapFleetMap`; provider details must not appear in user-facing copy.**
- [ ] **Step 4: Rerun the targeted test and `frontend/tests/amap-fleet-map.test.tsx`; confirm both pass.**
- [ ] **Step 5: Run `git diff --check` and inspect only Task 1 files.**

### Task 2: Permission redirect feedback and provenance badge

**Files:**

- Create: `frontend/src/components/navigation-notice.tsx`
- Create: `frontend/src/components/ui/data-source-badge.tsx`
- Modify: `frontend/src/auth/permission-gate.tsx`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/components/app-shell.tsx`
- Modify: `frontend/src/pages/fleet-live-map-page.tsx`
- Modify: `frontend/src/pages/report-issue-page.tsx`
- Modify: `frontend/src/styles/index.css`
- Test: `frontend/tests/role-routes.test.tsx`
- Test: `frontend/tests/data-source-badge.test.tsx`

**Interfaces:**

- Produces: redirect state `{ navigationNotice: { tone: "info", title: string, detail: string } }`.
- Produces: `DataSourceBadge({ provenance, detail })` supporting `LIVE`, `DEMO`, `MIXED`, and `FALLBACK`.

- [ ] **Step 1: Extend the employee fleet-route test to assert a visible explanation after redirect and add badge behavior tests with literal labels.**
- [ ] **Step 2: Run the two targeted test files and confirm they fail because redirect state and the shared badge do not exist.**
- [ ] **Step 3: Implement navigation notice state/rendering and apply the badge to the two map-linked employee/dispatcher surfaces without changing permissions.**
- [ ] **Step 4: Rerun both targeted tests and confirm green.**
- [ ] **Step 5: Run `git diff --check` and inspect only Task 2 files.**

### Task 3: Shared rescue-to-return timeline

**Files:**

- Create: `frontend/src/components/vehicle-operation-timeline.tsx`
- Modify: `frontend/src/components/fleet-sandbox-map.tsx`
- Modify: `frontend/src/components/driver-operation-status.tsx`
- Modify: `frontend/src/styles/vehicle-command-center.css`
- Test: `frontend/tests/vehicle-operation-timeline.test.tsx`
- Test: `frontend/tests/report-issue-page.test.tsx`
- Test: `frontend/tests/fleet-live-map-page.test.tsx`

**Interfaces:**

- Consumes: `VehicleOperationSnapshot.stages`, `rescue`, and `maintenance`.
- Produces: `VehicleOperationTimeline({ snapshot, compact })`, with report, replacement, rescue, tow, maintenance, inspection, and return status derived only from the snapshot.

- [ ] **Step 1: Write failing tests that render the same snapshot in full and compact modes and assert identical stage order and current-state semantics.**
- [ ] **Step 2: Run the three targeted files and confirm failure because the shared timeline is absent.**
- [ ] **Step 3: Extract lifecycle rendering into the shared component and reuse it in dispatcher and employee surfaces; do not synthesize progress when the snapshot is unavailable.**
- [ ] **Step 4: Rerun the targeted tests, then all frontend tests.**
- [ ] **Step 5: Run `npm run lint`, `npm run build`, the existing AMap browser test, and `git diff --check`.**

## Final verification

```powershell
Set-Location frontend
npm run test
npm run lint
npm run build
npm run test:e2e -- --grep "AMap|vehicle|report"
Set-Location ..
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' diff --check
```
