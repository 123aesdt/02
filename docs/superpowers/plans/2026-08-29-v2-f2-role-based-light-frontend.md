# CountyFlow V2-F2 Role-Based Light Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the existing CountyFlow SPA into a true-white, permission-driven, five-role product experience without duplicating the frontend or fabricating unavailable business data.

**Architecture:** Keep one React/Vite application. Adapt the authenticated Principal into a deterministic landing resolver and permission-filtered canonical navigation, then compose five thin role landing pages from shared workspace modules. Introduce semantic light tokens first, migrate the shell and common primitives, and then migrate existing pages including Graph and Monitoring.

**Tech Stack:** React, TypeScript, Vite, React Router, Vitest/jsdom, Playwright, existing fetch/API clients, existing Lucide icons, existing CSS architecture.

**Spec:** `docs/superpowers/specs/2026-08-29-v2-f2-role-based-light-frontend-design.md`

## Global Constraints

- Read `AGENTS.md`, the design spec, `docs/frontend_role_ux.md`, `docs/frontend_light_theme.md`, and `docs/permissions.md` before implementation.
- Use behavior-level TDD: write one failing test, run and observe RED, implement the smallest real behavior, then rerun GREEN.
- Do not change React, Vite, Router, state/API patterns, or add a large UI/graph framework.
- `#FFFFFF` is the exact application background. Sidebar, Topbar, dialog, table, Graph, and Monitoring must all be light before release.
- Backend authorization remains final. Navigation hiding never replaces route/action permission gates or direct-request 401/403.
- API mode uses real data or explicit Empty / `NOT EXPOSED` / failure states. It never falls back to Mock or renders fixture KPI values.
- Production cannot contain a self-service role switch. Development preview must be visibly `DEV AUTH` and obtain a server-issued development session.
- Do not implement backend read-model gaps, new business endpoints, new agents, databases, IAM, maps, driver apps, or other out-of-scope products under this plan.
- Preserve existing Graph Memory, Shared Memory, Runtime Thread, Checkpoint, Runtime Override, Override History, Monitoring, and Audit capabilities for permitted roles.
- Do not run `git commit`, create a branch, or otherwise mutate Git history unless the user separately authorizes it. Each task still ends with a diff/reviewer checkpoint.
- After every phase inspect `git diff`; before completion run the full required frontend/backend gates and `git -c safe.directory=<workspace> diff --check`.

## Planned file map

### Authentication and navigation

- Create `frontend/src/auth/principal-view.ts`: localized roles, primary role selection, Principal view adapter.
- Create `frontend/src/navigation/navigation-model.ts`: canonical navigation types.
- Create `frontend/src/navigation/navigation-registry.tsx`: icon-bearing canonical route metadata.
- Create `frontend/src/navigation/navigation-resolver.ts`: permission filter and role ordering.
- Create `frontend/src/navigation/role-landing-resolver.ts`: deterministic default route.
- Create `frontend/src/components/role-navigation.tsx`: accessible resolved navigation renderer.
- Modify `frontend/src/auth/auth-provider.tsx`: expose supported development-session refresh for dev preview only.
- Modify `frontend/src/auth/auth-session-banner.tsx`: white role identity/session treatment.
- Modify `frontend/src/app/router.tsx`: resolver plus role routes and unchanged guards.
- Modify `frontend/src/components/app-shell.tsx`: consume resolved navigation and Principal identity.

### Theme and shared UI

- Create `frontend/src/styles/tokens.css`: semantic colors, spacing, radius, typography, motion.
- Modify `frontend/src/styles/index.css`: token consumption and light common layouts.
- Modify `frontend/src/styles/memory-control.css`: light Memory/Graph/Inspector surfaces.
- Create `frontend/src/components/ui/status-badge.tsx`: normalized text/dot/icon status.
- Create `frontend/src/components/ui/empty-state.tsx`: Empty/Not Exposed/Forbidden/Unavailable variants.
- Create `frontend/src/components/ui/skeleton.tsx`: reduced-motion-aware section skeleton.
- Create `frontend/src/components/ui/data-table.tsx`: shared table container and state slots.
- Create `frontend/src/components/workspace/workspace-section.tsx`: open section primitive.
- Create `frontend/src/components/workspace/task-queue.tsx`: reusable task/review queue renderer.
- Create `frontend/src/components/workspace/evidence-panel.tsx`: progressive evidence disclosure.
- Create `frontend/src/components/workspace/system-health.tsx`: operations summary.
- Create `frontend/src/components/workspace/audit-timeline.tsx`: read-only audit timeline.

### Role workspaces

- Create `frontend/src/pages/dispatcher-workspace-page.tsx`.
- Create `frontend/src/pages/supervisor-workspace-page.tsx`.
- Create `frontend/src/pages/operations-page.tsx`.
- Create `frontend/src/pages/audit-page.tsx`.
- Create `frontend/src/pages/admin-overview-page.tsx`.
- Create `frontend/src/pages/my-tasks-page.tsx`.
- Create `frontend/src/pages/review-queue-page.tsx`.
- Create `frontend/src/pages/runtime-page.tsx`.

### Read adapters and tests

- Create `frontend/src/types/workspace.ts`: role workspace view types and provenance.
- Create `frontend/src/services/api/workspace-read-client.ts`: narrow optional read contracts; returns typed `NOT_EXPOSED`, never fixtures.
- Create/modify focused tests under `frontend/tests/` named in each task.
- Create `frontend/e2e/role-based-light-ui.spec.ts`: five-role, light-theme, authorization, responsive, and screenshot QA.
- Create implementation-time evidence only under `docs/verification/frontend-role-ui/`.

---

### Task 1: Principal view and role landing resolution

**Files:**
- Create: `frontend/src/auth/principal-view.ts`
- Create: `frontend/src/navigation/role-landing-resolver.ts`
- Test: `frontend/tests/role-landing.test.ts`

**Interfaces:**
- Consumes: `Principal` from `frontend/src/auth/session.ts`; `Role` from `frontend/src/auth/permissions.ts`.
- Produces: `localizeRole(role): string`, `primaryRole(roles): Role | null`, `resolveRoleLanding(roles): "/overview" | "/supervisor" | "/operations" | "/audit" | "/workspace" | null`.

- [ ] **Step 1: Write the failing resolver tests**

```ts
import { describe, expect, it } from "vitest";
import { localizeRole, primaryRole } from "../src/auth/principal-view";
import { resolveRoleLanding } from "../src/navigation/role-landing-resolver";

describe("role landing", () => {
  it("maps every role to a distinct default", () => {
    expect(resolveRoleLanding(["DISPATCHER"])).toBe("/workspace");
    expect(resolveRoleLanding(["SUPERVISOR"])).toBe("/supervisor");
    expect(resolveRoleLanding(["OPERATOR"])).toBe("/operations");
    expect(resolveRoleLanding(["AUDITOR"])).toBe("/audit");
    expect(resolveRoleLanding(["ADMIN"])).toBe("/overview");
  });
  it("uses the approved multi-role priority", () => {
    expect(primaryRole(["DISPATCHER", "SUPERVISOR"])).toBe("SUPERVISOR");
    expect(localizeRole("SUPERVISOR")).toBe("调度主管");
  });
});
```

- [ ] **Step 2: Run RED**

Run: `npm test -- tests/role-landing.test.ts`

Expected: FAIL because both modules are missing.

- [ ] **Step 3: Implement the approved maps without granting permissions**

```ts
const ROLE_PRIORITY: Role[] = ["ADMIN", "SUPERVISOR", "OPERATOR", "AUDITOR", "DISPATCHER"];
const ROLE_LANDINGS: Record<Role, RoleLanding> = {
  ADMIN: "/overview", SUPERVISOR: "/supervisor", OPERATOR: "/operations",
  AUDITOR: "/audit", DISPATCHER: "/workspace",
};
```

Filter unknown Principal role strings; return `null` when no canonical role exists. Do not derive or add permissions.

- [ ] **Step 4: Run GREEN and regression**

Run: `npm test -- tests/role-landing.test.ts tests/auth-session.test.tsx`

Expected: PASS.

- [ ] **Step 5: Inspect diff checkpoint**

Run: `git diff -- frontend/src/auth/principal-view.ts frontend/src/navigation/role-landing-resolver.ts frontend/tests/role-landing.test.ts`

Expected: only pure mapping/resolver code and its tests.

### Task 2: Canonical permission-driven navigation

**Files:**
- Create: `frontend/src/navigation/navigation-model.ts`
- Create: `frontend/src/navigation/navigation-registry.tsx`
- Create: `frontend/src/navigation/navigation-resolver.ts`
- Create: `frontend/src/components/role-navigation.tsx`
- Test: `frontend/tests/role-navigation.test.tsx`

**Interfaces:**
- Consumes: `Permission`, `Role`, and Task 1 `primaryRole`.
- Produces: `NavigationItem`, `resolveNavigation({ roles, permissions }): NavigationGroup[]`, and `<RoleNavigation groups collapsed />`.

- [ ] **Step 1: Write failing role navigation tests**

```tsx
it("test_dispatcher_navigation hides monitoring and runtime", () => {
  const groups = resolveNavigation({ roles: ["DISPATCHER"], permissions: permissionsForRole("DISPATCHER") });
  expect(flattenLabels(groups)).toEqual(["调度工作台", "异常中心", "智能调度", "运单管理", "我的任务"]);
  expect(flattenLabels(groups)).not.toContain("系统监控");
});

it("test_operator_monitoring_default excludes dispatch write", () => {
  const groups = resolveNavigation({ roles: ["OPERATOR"], permissions: permissionsForRole("OPERATOR") });
  expect(flattenLabels(groups)).toContain("运行中心");
  expect(flattenLabels(groups)).not.toContain("智能调度");
});

it("test_permission_driven_navigation uses permissions as truth", () => {
  const groups = resolveNavigation({ roles: ["DISPATCHER"], permissions: ["monitor:read"] });
  expect(flattenLabels(groups)).toContain("系统监控");
  expect(flattenLabels(groups)).not.toContain("智能调度");
});

it("test_multi_role_permissions keeps the server permission union", () => {
  const groups = resolveNavigation({
    roles: ["DISPATCHER", "OPERATOR"],
    permissions: ["dispatch:read", "dispatch:create", "monitor:read"],
  });
  expect(flattenLabels(groups)).toContain("智能调度");
  expect(flattenLabels(groups)).toContain("系统监控");
  expect(flattenLabels(groups)).not.toContain("Runtime");
});
```

- [ ] **Step 2: Run RED**

Run: `npm test -- tests/role-navigation.test.tsx`

Expected: FAIL because registry/resolver/components are missing.

- [ ] **Step 3: Implement one canonical registry and pure resolver**

Each registry item declares exact permissions and `primary` or `contextual` role ordering. Filter with `requiredPermissions.every(permissionSet.has)`. Do not write `role === "ADMIN"` in the renderer and do not invent permission implication.

- [ ] **Step 4: Implement accessible navigation rendering**

Render group labels, active `NavLink`, collapsed accessible name/tooltip, and exact Chinese product labels. An empty group is omitted.

- [ ] **Step 5: Run GREEN**

Run: `npm test -- tests/role-navigation.test.tsx`

Expected: Dispatcher, Supervisor, Operator, Auditor, Admin, and multi-role cases PASS.

- [ ] **Step 6: Inspect diff checkpoint**

Run: `git diff -- frontend/src/navigation frontend/src/components/role-navigation.tsx frontend/tests/role-navigation.test.tsx`

Expected: one registry, no copied per-role navigation arrays.

### Task 3: Semantic light tokens and common source scan

**Files:**
- Create: `frontend/src/styles/tokens.css`
- Modify: `frontend/src/main.tsx`
- Test: `frontend/tests/light-theme-contract.test.ts`

**Interfaces:**
- Produces the exact CSS custom properties in `docs/frontend_light_theme.md` for every later style task.

- [ ] **Step 1: Write the failing token contract test**

```ts
it("test_light_theme_app_shell defines true white and semantic tokens", () => {
  const css = readFileSync(resolve("src/styles/tokens.css"), "utf8");
  expect(css).toMatch(/--background:\s*#ffffff/i);
  for (const token of ["surface-primary", "border", "text-primary", "brand", "danger", "focus-ring"]) {
    expect(css).toContain(`--${token}:`);
  }
  expect(css).toContain("color-scheme: light");
});
```

- [ ] **Step 2: Run RED**

Run: `npm test -- tests/light-theme-contract.test.ts`

Expected: FAIL because `tokens.css` does not exist.

- [ ] **Step 3: Add exact tokens and import before existing styles**

Copy the normative values from `docs/frontend_light_theme.md`; do not approximate `#FFFFFF` with a warm white. Import `tokens.css` before `index.css` and `memory-control.css` in `main.tsx`.

- [ ] **Step 4: Run GREEN and build**

Run: `npm test -- tests/light-theme-contract.test.ts`

Run: `npm run build`

Expected: PASS; production build succeeds without a new dependency.

- [ ] **Step 5: Inspect diff checkpoint**

Run: `git diff -- frontend/src/styles/tokens.css frontend/src/main.tsx frontend/tests/light-theme-contract.test.ts`

Expected: token definitions and import only; no page behavior change.

### Task 4: Complete light App Shell and Principal identity

**Files:**
- Modify: `frontend/src/components/app-shell.tsx`
- Modify: `frontend/src/auth/auth-session-banner.tsx`
- Modify: `frontend/src/styles/index.css`
- Test: `frontend/tests/app-shell-role.test.tsx`
- Test: `frontend/tests/light-theme-contract.test.ts`

**Interfaces:**
- Consumes: Task 1 Principal view and Task 2 `<RoleNavigation>`.
- Produces: white `<AppShell>` with localized name/role and responsive collapsed state.

- [ ] **Step 1: Write failing shell tests**

```tsx
it("test_light_theme_sidebar renders resolved links and identity", () => {
  renderShellAs("DISPATCHER");
  expect(screen.getByText("Audit DISPATCHER")).toBeVisible();
  expect(screen.getByText("调度员")).toBeVisible();
  expect(screen.queryByRole("link", { name: "系统监控" })).not.toBeInTheDocument();
});

it("test_light_theme_app_shell has no generic admin avatar", () => {
  renderShellAs("OPERATOR");
  expect(screen.queryByText("管")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run RED**

Run: `npm test -- tests/app-shell-role.test.tsx tests/light-theme-contract.test.ts`

Expected: FAIL because AppShell still uses static nav and generic avatar/dark styles.

- [ ] **Step 3: Replace static nav with RoleNavigation**

Read `useAuth()`, adapt Principal, render only resolved groups, and keep route title logic in a focused helper. Preserve Sidebar collapse behavior and accessible button name.

- [ ] **Step 4: Convert the complete shell to tokens**

Set Body/App Shell/Main/Sidebar/Topbar/page background to `var(--background)`; use borders and the documented selected/hover/focus states. Remove dark gradients and hard-coded online worker claims not backed by data.

- [ ] **Step 5: Run GREEN**

Run: `npm test -- tests/app-shell-role.test.tsx tests/auth-session.test.tsx tests/light-theme-contract.test.ts`

Run: `npm run build`

Expected: PASS.

- [ ] **Step 6: Inspect diff checkpoint**

Run: `git diff -- frontend/src/components/app-shell.tsx frontend/src/auth/auth-session-banner.tsx frontend/src/styles/index.css`

Expected: one coherent white shell; no dark Sidebar/Topbar residual.

### Task 5: Route resolver, role pages, and direct authorization

**Files:**
- Modify: `frontend/src/app/router.tsx`
- Create: `frontend/src/pages/dispatcher-workspace-page.tsx`
- Create: `frontend/src/pages/supervisor-workspace-page.tsx`
- Create: `frontend/src/pages/operations-page.tsx`
- Create: `frontend/src/pages/audit-page.tsx`
- Create: `frontend/src/pages/admin-overview-page.tsx`
- Test: `frontend/tests/role-routes.test.tsx`

**Interfaces:**
- Consumes: `resolveRoleLanding`, existing `RequirePermission`.
- Produces: `/` resolver and five guarded landing routes.

- [ ] **Step 1: Write failing route tests**

```tsx
it("test_dispatcher_default_workspace", async () => {
  await renderRouterAs("DISPATCHER", "/");
  expect(await screen.findByRole("heading", { name: "调度工作台" })).toBeVisible();
});

it("test_unauthorized_route", async () => {
  await renderRouterAs("DISPATCHER", "/operations");
  expect(await screen.findByRole("heading", { name: "无权访问" })).toBeVisible();
});
```

- [ ] **Step 2: Run RED**

Run: `npm test -- tests/role-routes.test.tsx`

Expected: FAIL because routes/pages do not exist.

- [ ] **Step 3: Add thin semantic landing shells**

Each page initially renders its Chinese title and shared state boundary only. Guard routes with `dispatch:read`, `dispatch:review`, `monitor:read`, `audit:read`, and `system:admin` respectively. Do not add fake KPI values.

- [ ] **Step 4: Add authenticated root redirect**

Wait for AuthProvider to reach authenticated/expired/anonymous. Redirect only authenticated Principals with a canonical role; keep explicit session state otherwise. Prevent redirect loops.

- [ ] **Step 5: Run GREEN and existing auth regression**

Run: `npm test -- tests/role-routes.test.tsx tests/auth-session.test.tsx`

Expected: PASS.

- [ ] **Step 6: Inspect diff checkpoint**

Run: `git diff -- frontend/src/app/router.tsx frontend/src/pages frontend/tests/role-routes.test.tsx`

Expected: distinct defaults with shared components, not cloned dashboard markup.

### Task 6: Development identity preview with production exclusion

**Files:**
- Create: `frontend/src/auth/dev-role-preview.tsx`
- Modify: `frontend/src/auth/auth-provider.tsx`
- Modify: `frontend/src/auth/auth-session-banner.tsx`
- Test: `frontend/tests/dev-role-preview.test.tsx`

**Interfaces:**
- Consumes: runtime environment and server development-session endpoint.
- Produces: a development-only `DEV AUTH` control that requests a new server-issued session; no local permission construction.

- [ ] **Step 1: Write failing environment tests**

```tsx
it("test_production_no_role_switcher", () => {
  renderPreview({ mode: "production", authenticationMode: "oidc_jwt" });
  expect(screen.queryByText("DEV AUTH")).not.toBeInTheDocument();
});

it("test_dev_role_preview_marked", () => {
  renderPreview({ mode: "development", authenticationMode: "development_jwt" });
  expect(screen.getByText("DEV AUTH")).toBeVisible();
});
```

- [ ] **Step 2: Run RED**

Run: `npm test -- tests/dev-role-preview.test.tsx`

Expected: FAIL because component/provider method is missing.

- [ ] **Step 3: Implement server-issued preview only**

Render the current identity as visibly `DEV AUTH` in local/docker-dev/test. The current endpoint does not accept a preview role, so do not render an interactive role selector under this task. Automated tests may inject server-shaped test Principals. Enabling an interactive selector requires the separately approved G2 development-only contract recorded in the design spec; do not modify G2 or fabricate claims under this task.

- [ ] **Step 4: Run GREEN and production build scan**

Run: `npm test -- tests/dev-role-preview.test.tsx tests/auth-session.test.tsx`

Run: `npm run build`

Expected: PASS; production render has no preview control.

- [ ] **Step 5: Inspect diff checkpoint**

Run: `git diff -- frontend/src/auth frontend/tests/dev-role-preview.test.tsx`

Expected: no local `permissionsForRole()` call in production code.

### Task 7: Shared light UI state primitives

**Files:**
- Create: `frontend/src/components/ui/status-badge.tsx`
- Create: `frontend/src/components/ui/empty-state.tsx`
- Create: `frontend/src/components/ui/skeleton.tsx`
- Create: `frontend/src/components/ui/data-table.tsx`
- Create: `frontend/src/components/workspace/workspace-section.tsx`
- Modify: `frontend/src/styles/index.css`
- Test: `frontend/tests/workspace-ui.test.tsx`

**Interfaces:**
- Produces: `StatusBadge`, `EmptyState`, `Skeleton`, `DataTable`, and `WorkspaceSection` used by all later pages.

- [ ] **Step 1: Write failing semantic state tests**

```tsx
it("renders text and a non-color marker for status", () => {
  render(<StatusBadge status="REVIEW_REQUIRED" />);
  expect(screen.getByText("需复核")).toBeVisible();
  expect(screen.getByText("需复核").closest("span")).toHaveAttribute("data-tone", "warning");
});

it("distinguishes empty from not exposed", () => {
  const { rerender } = render(<EmptyState kind="empty" title="当前没有待处理异常" />);
  expect(screen.getByText("当前没有待处理异常")).toBeVisible();
  rerender(<EmptyState kind="not-exposed" title="业务汇总接口未开放" />);
  expect(screen.getByText("业务汇总接口未开放")).toHaveAttribute("data-state", "not-exposed");
});

it("test_light_theme_table exposes real headers and state slots", () => {
  render(<DataTable caption="待处理任务" columns={[{ key: "task", label: "任务" }]} rows={[]} empty={<EmptyState kind="empty" title="当前没有待处理任务" />} />);
  expect(screen.getByRole("columnheader", { name: "任务" })).toBeVisible();
  expect(screen.getByText("当前没有待处理任务")).toBeVisible();
});
```

- [ ] **Step 2: Run RED**

Run: `npm test -- tests/workspace-ui.test.tsx`

Expected: FAIL because primitives are missing.

- [ ] **Step 3: Implement semantic primitives and all interaction states**

Use tokens only. Skeleton honors reduced motion; DataTable has caption/header/body and loading/empty/error slots; StatusBadge maps all specified Chinese statuses and retains canonical value for assistive text.

- [ ] **Step 4: Run GREEN**

Run: `npm test -- tests/workspace-ui.test.tsx`

Expected: PASS.

- [ ] **Step 5: Inspect diff checkpoint**

Run: `git diff -- frontend/src/components/ui frontend/src/components/workspace/workspace-section.tsx frontend/src/styles/index.css`

Expected: no new dark values and no decorative image assets.

### Task 8: Truthful workspace read boundary

**Files:**
- Create: `frontend/src/types/workspace.ts`
- Create: `frontend/src/services/api/workspace-read-client.ts`
- Test: `frontend/tests/workspace-read-client.test.ts`

**Interfaces:**
- Produces: `DataProvenance = "LIVE" | "DEMO" | "VERIFIED" | "STALE" | "NOT_EXPOSED"`, `ReadState<T>`, and narrow read methods that can explicitly return `NOT_EXPOSED`.

- [ ] **Step 1: Write failing no-fallback tests**

```ts
it("test_api_mode_no_fake_role_data", async () => {
  const client = createWorkspaceReadClient({ fetchImpl: failingFetch(404) });
  await expect(client.getDispatcherWorkspace()).resolves.toEqual({
    state: "NOT_EXPOSED", data: null,
  });
});
```

- [ ] **Step 2: Run RED**

Run: `npm test -- tests/workspace-read-client.test.ts`

Expected: FAIL because types/client are missing.

- [ ] **Step 3: Implement explicit absent-contract behavior**

Do not call the existing Mock workspace service in API mode. Map 404/501 for an approved optional read projection to `NOT_EXPOSED`; map 401, 403, 5xx, abort, and network errors to distinct states. Do not catch all errors as empty.

- [ ] **Step 4: Run GREEN**

Run: `npm test -- tests/workspace-read-client.test.ts tests/workspace-services.test.ts`

Expected: PASS.

- [ ] **Step 5: Inspect diff checkpoint**

Run: `git diff -- frontend/src/types/workspace.ts frontend/src/services/api/workspace-read-client.ts frontend/tests/workspace-read-client.test.ts`

Expected: no invented endpoint response fields beyond the spec's adapter boundary.

### Task 9: Dispatcher workspace and My Tasks truth boundary

**Files:**
- Create: `frontend/src/components/workspace/task-queue.tsx`
- Modify: `frontend/src/pages/dispatcher-workspace-page.tsx`
- Create: `frontend/src/pages/my-tasks-page.tsx`
- Modify: `frontend/src/app/router.tsx`
- Test: `frontend/tests/dispatcher-workspace.test.tsx`

**Interfaces:**
- Consumes: Task 7 primitives and Task 8 `ReadState<DispatcherWorkspaceView>`.
- Produces: shared `TaskQueue` plus Dispatcher landing/My Tasks pages.

- [ ] **Step 1: Write failing Dispatcher behavior tests**

```tsx
it("test_dispatcher_default_workspace prioritizes work", () => {
  renderDispatcher(liveWorkspaceFixture);
  expect(screen.getByRole("heading", { name: "调度工作台" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "我的待办" })).toBeVisible();
  expect(screen.getByRole("link", { name: "发起智能调度" })).toBeVisible();
});

it("does not show zero when ownership projection is unavailable", () => {
  renderDispatcher({ state: "NOT_EXPOSED", data: null });
  expect(screen.getByText("我的任务数据接口尚未开放")).toBeVisible();
  expect(screen.queryByText(/^0$/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run RED**

Run: `npm test -- tests/dispatcher-workspace.test.tsx`

Expected: FAIL because composition/queue is missing.

- [ ] **Step 3: Implement shared queue and Dispatcher composition**

Render work overview, My Tasks, dispatching now, AI recommendations, and recent completion only from supplied live data. In the current backend state, render mature `NOT EXPOSED` sections and preserve the real dispatch CTA; do not use `workspace-data.ts` in API mode.

- [ ] **Step 4: Run GREEN**

Run: `npm test -- tests/dispatcher-workspace.test.tsx tests/role-navigation.test.tsx`

Expected: PASS.

- [ ] **Step 5: Inspect diff checkpoint**

Run: `git diff -- frontend/src/components/workspace/task-queue.tsx frontend/src/pages/dispatcher-workspace-page.tsx frontend/src/pages/my-tasks-page.tsx`

Expected: one queue implementation and no fake owner data.

### Task 10: Fix Anomalies and Orders API truth before light migration

**Files:**
- Modify: `frontend/src/pages/anomalies-page.tsx`
- Modify: `frontend/src/pages/orders-page.tsx`
- Modify: `frontend/src/hooks/use-workspace-data.ts`
- Test: `frontend/tests/business-pages-data-truth.test.tsx`

**Interfaces:**
- Consumes: Task 7 state primitives.
- Produces: API-mode pages that show `NOT EXPOSED`, never fixture KPI values.

- [ ] **Step 1: Write failing API-mode tests**

```tsx
it("hides fixture anomaly KPIs in API mode", () => {
  renderApiMode(<AnomaliesPage />);
  expect(screen.getByText("异常列表接口尚未开放")).toBeVisible();
  expect(screen.queryByText("17")).not.toBeInTheDocument();
});

it("hides fixture order KPIs in API mode", () => {
  renderApiMode(<OrdersPage />);
  expect(screen.getByText("运单列表接口尚未开放")).toBeVisible();
  expect(screen.queryByText("1,284")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run RED**

Run: `npm test -- tests/business-pages-data-truth.test.tsx`

Expected: FAIL because both pages currently render static KPI values in API mode.

- [ ] **Step 3: Separate Mock and API render states**

Keep labelled Demo fixtures only in Mock mode. In API mode use the optional read boundary or `NOT EXPOSED`. Convert tables/filters/drawers to light primitives without changing existing Mock search/filter behavior.

- [ ] **Step 4: Run GREEN**

Run: `npm test -- tests/business-pages-data-truth.test.tsx tests/workspace-services.test.ts tests/v2-product-surfaces.test.tsx`

Expected: PASS.

- [ ] **Step 5: Inspect diff checkpoint**

Run: `git diff -- frontend/src/pages/anomalies-page.tsx frontend/src/pages/orders-page.tsx frontend/src/hooks/use-workspace-data.ts`

Expected: no fixture metrics on API branches.

### Task 11: Dispatcher form, execution explanation, and evidence hierarchy

**Files:**
- Modify: `frontend/src/pages/dispatch-start-page.tsx`
- Modify: `frontend/src/pages/api-dispatch-detail-page.tsx`
- Create: `frontend/src/components/workspace/evidence-panel.tsx`
- Modify: `frontend/src/components/agent-pipeline.tsx`
- Test: `frontend/tests/dispatch-role-ux.test.tsx`

**Interfaces:**
- Consumes: existing `createDispatchTask`, task result/events, Task 7 primitives.
- Produces: typed form mapped only to the existing request contract and business explanation hierarchy.

- [ ] **Step 1: Write failing form/evidence tests**

```tsx
it("submits user-entered existing dispatch fields", async () => {
  renderDispatchStart(createTaskSpy);
  await user.type(screen.getByLabelText("异常描述"), "雨天道路湿滑");
  await user.click(screen.getByRole("button", { name: "发起 AI 调度" }));
  expect(createTaskSpy).toHaveBeenCalledTimes(1);
});

it("shows eight business steps without raw JSON", () => {
  renderDispatchDetail(realEventFixture);
  expect(screen.getByText("图关系分析")).toBeVisible();
  expect(screen.queryByText(/\{\s*"graph_memory_facts"/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run RED**

Run: `npm test -- tests/dispatch-role-ux.test.tsx`

Expected: FAIL because start page is a fixed one-click sample and detail exposes technical event fields directly.

- [ ] **Step 3: Implement only fields supported by the current create DTO**

Map anomaly description, vehicle, route, priority, and optional context only when each maps to the existing `CreateDispatchTaskRequest`. If a requested product field has no DTO field, omit its control and record it as `NOT EXPOSED`; do not extend backend in this task.

- [ ] **Step 4: Compose business execution and progressive evidence**

Translate the canonical eight agents to Chinese business steps. Show recommendation, history, Graph relation summary, weather/road, capacity, candidates, decision, and audit through `EvidencePanel`; retain technical detail under an advanced Inspector for permitted users.

- [ ] **Step 5: Run GREEN and existing dispatch regressions**

Run: `npm test -- tests/dispatch-role-ux.test.tsx tests/dispatch-submission.test.ts tests/dispatch-v2-evidence.test.tsx tests/task-events-lifecycle.test.tsx`

Expected: PASS.

- [ ] **Step 6: Inspect diff checkpoint**

Run: `git diff -- frontend/src/pages/dispatch-start-page.tsx frontend/src/pages/api-dispatch-detail-page.tsx frontend/src/components/workspace/evidence-panel.tsx frontend/src/components/agent-pipeline.tsx`

Expected: no backend contract expansion and no raw JSON as default product content.

### Task 12: Supervisor Review Queue and Runtime Intervention placement

**Files:**
- Modify: `frontend/src/pages/supervisor-workspace-page.tsx`
- Create: `frontend/src/pages/review-queue-page.tsx`
- Modify: `frontend/src/components/runtime-workbench.tsx`
- Modify: `frontend/src/components/runtime-override-dialog.tsx`
- Modify: `frontend/src/components/runtime-override-history.tsx`
- Modify: `frontend/src/app/router.tsx`
- Test: `frontend/tests/supervisor-workspace.test.tsx`

**Interfaces:**
- Consumes: `dispatch:review`, `runtime:read`, `runtime:override`, existing backend intervention context/history.
- Produces: Supervisor composition, truthful Review Queue boundary, permission-gated Danger Zone.

- [ ] **Step 1: Write failing Supervisor tests**

```tsx
it("test_supervisor_review_visible", () => {
  renderSupervisor({ reviewState: "NOT_EXPOSED" });
  expect(screen.getByRole("heading", { name: "待人工复核" })).toBeVisible();
  expect(screen.getByText("复核操作接口尚未开放")).toBeVisible();
});

it("test_supervisor_runtime_override_visible", () => {
  renderRuntimeAs(["runtime:read", "runtime:override"], eligibleFixture);
  expect(screen.getByRole("button", { name: "进入强干预" })).toBeVisible();
});

it("test_dispatcher_no_runtime_override", () => {
  renderRuntimeAs(["dispatch:read"], eligibleFixture);
  expect(screen.queryByRole("button", { name: "进入强干预" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run RED**

Run: `npm test -- tests/supervisor-workspace.test.tsx`

Expected: FAIL because Supervisor pages do not exist and Runtime workbench is not composed as specified.

- [ ] **Step 3: Build Review Queue shell without local review transitions**

Use `TaskQueue` columns Task/AI Decision/Risk/Reason/Vehicle/Route/State/Wait Time. With no approved review API, render `NOT EXPOSED` and no confirm/reject handler. When a separate backend read/action contract is approved, its client must be added with a new TDD task before actions are enabled.

- [ ] **Step 4: Migrate intervention to the light Danger Zone**

Keep backend eligibility, expected state version/next node, 409 recovery, focus trap, Escape, focus restoration, loading/double-submit protection, and history refresh. Final confirmation uses Danger style, never teal primary.

- [ ] **Step 5: Run GREEN and Runtime regressions**

Run: `npm test -- tests/supervisor-workspace.test.tsx tests/runtime-workbench.test.tsx tests/runtime-override-client.test.ts tests/runtime-thread-panel.test.tsx`

Expected: PASS.

- [ ] **Step 6: Inspect diff checkpoint**

Run: `git diff -- frontend/src/pages/supervisor-workspace-page.tsx frontend/src/pages/review-queue-page.tsx frontend/src/components/runtime-*`

Expected: no fake review mutation and no Dispatcher override affordance.

### Task 13: Operator workspace and Runtime read surface

**Files:**
- Create: `frontend/src/components/workspace/system-health.tsx`
- Modify: `frontend/src/pages/operations-page.tsx`
- Create: `frontend/src/pages/runtime-page.tsx`
- Modify: `frontend/src/app/router.tsx`
- Test: `frontend/tests/operator-workspace.test.tsx`

**Interfaces:**
- Consumes: existing observability summary and current runtime-by-ID APIs.
- Produces: Operator-first system health and a truthful global Runtime list boundary.

- [ ] **Step 1: Write failing Operator tests**

```tsx
it("test_operator_monitoring_default", () => {
  renderOperations(liveObservabilityFixture);
  expect(screen.getByRole("heading", { name: "运行中心" })).toBeVisible();
  expect(screen.getByText("Worker Pending")).toBeVisible();
});

it("test_operator_no_dispatch_write", () => {
  renderOperations(liveObservabilityFixture);
  expect(screen.queryByRole("link", { name: "发起智能调度" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run RED**

Run: `npm test -- tests/operator-workspace.test.tsx`

Expected: FAIL because operations composition/system health are missing.

- [ ] **Step 3: Compose live operations modules**

Use existing `/observability/summary` values for QPS/P95/error/pending/lag/dependencies and preserve `STALE`, `UNAVAILABLE`, and `NO_PERMISSION`. Runtime list page shows `NOT EXPOSED` until a bounded list endpoint exists; it may still accept an explicit thread/task ID for existing reads.

- [ ] **Step 4: Run GREEN**

Run: `npm test -- tests/operator-workspace.test.tsx tests/monitoring-live.test.tsx tests/observability-client.test.ts`

Expected: PASS.

- [ ] **Step 5: Inspect diff checkpoint**

Run: `git diff -- frontend/src/components/workspace/system-health.tsx frontend/src/pages/operations-page.tsx frontend/src/pages/runtime-page.tsx`

Expected: no dispatch/review/override/mutation controls.

### Task 14: Auditor immutable timeline and Admin product overview

**Files:**
- Create: `frontend/src/components/workspace/audit-timeline.tsx`
- Create: `frontend/src/services/api/security-audit-client.ts`
- Modify: `frontend/src/pages/audit-page.tsx`
- Modify: `frontend/src/pages/admin-overview-page.tsx`
- Test: `frontend/tests/auditor-admin-workspaces.test.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/security/audit`, existing task-scoped audit/override/Memory projections.
- Produces: read-only Audit timeline and productized Admin summary links.

- [ ] **Step 1: Write failing Auditor/Admin tests**

```tsx
it("test_auditor_read_only", () => {
  renderAudit(securityAuditFixture);
  expect(screen.getByRole("heading", { name: "审计中心" })).toBeVisible();
  expect(screen.queryByRole("button", { name: /确认|拒绝|修改|干预|发起/ })).not.toBeInTheDocument();
});

it("test_admin_full_navigation renders product summaries", () => {
  renderAdminOverview();
  for (const title of ["业务健康", "智能体", "记忆", "运行", "可观测性", "治理与安全"]) {
    expect(screen.getByText(title)).toBeVisible();
  }
  expect(screen.queryByText(/Redis key|PromQL|raw checkpoint/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run RED**

Run: `npm test -- tests/auditor-admin-workspaces.test.tsx`

Expected: FAIL because timeline/client/compositions are missing.

- [ ] **Step 3: Implement typed security audit read and immutable timeline**

Map the existing bounded safe event records. For business/Memory/Override aggregate categories not exposed globally, show `NOT EXPOSED`; do not merge fixtures. No audit mutation or retry handler exists.

- [ ] **Step 4: Implement Admin overview as links, not duplicated pages**

Use live/verified/not-exposed summaries and links to shared pages. Keep raw technical fields behind existing approved Inspectors and do not invent IAM navigation.

- [ ] **Step 5: Run GREEN**

Run: `npm test -- tests/auditor-admin-workspaces.test.tsx tests/role-navigation.test.tsx`

Expected: PASS.

- [ ] **Step 6: Inspect diff checkpoint**

Run: `git diff -- frontend/src/components/workspace/audit-timeline.tsx frontend/src/services/api/security-audit-client.ts frontend/src/pages/audit-page.tsx frontend/src/pages/admin-overview-page.tsx`

Expected: read-only Auditor and productized Admin without debug dump.

### Task 15: Existing common pages and controls light migration

**Files:**
- Modify: `frontend/src/pages/agents-page.tsx`
- Modify: `frontend/src/pages/memory-page.tsx`
- Modify: `frontend/src/pages/api-dispatch-detail-page.tsx`
- Modify: `frontend/src/components/checkpoint-timeline.tsx`
- Modify: `frontend/src/components/runtime-thread-panel.tsx`
- Modify: `frontend/src/components/shared-memory-control.tsx`
- Modify: `frontend/src/styles/index.css`
- Test: `frontend/tests/existing-pages-light.test.tsx`

**Interfaces:**
- Consumes: light tokens/primitives; retains all existing data hooks and permission behavior.
- Produces: light Agents/Memory/Dispatch/Runtime common surfaces.

- [ ] **Step 1: Write failing structural tests**

```tsx
it("keeps Memory layers while using localized tabs", () => {
  renderMemoryApi();
  expect(screen.getByRole("tab", { name: /向量记忆/ })).toBeVisible();
  expect(screen.getByText("当前后端未暴露 Vector Memory 浏览 API")).toBeVisible();
});

it("keeps checkpoint and override evidence", () => {
  renderDispatchDetail(runtimeFixture);
  expect(screen.getByRole("region", { name: "Runtime Thread" })).toBeVisible();
  expect(screen.getByText("Override History")).toBeVisible();
});
```

- [ ] **Step 2: Run RED**

Run: `npm test -- tests/existing-pages-light.test.tsx`

Expected: FAIL on new labels/structure before migration.

- [ ] **Step 3: Migrate page structure and complete states**

Replace nested dark cards with open sections, tables, rails, timelines, and Inspectors. Preserve current task IDs, live events, Memory fact keys, Runtime semantics, permission notes, and verified labels.

- [ ] **Step 4: Run GREEN and focused regressions**

Run: `npm test -- tests/existing-pages-light.test.tsx tests/memory-control-plane.test.tsx tests/checkpoint-timeline.test.tsx tests/dispatch-v2-evidence.test.tsx tests/v2-product-surfaces.test.tsx`

Expected: PASS.

- [ ] **Step 5: Inspect diff checkpoint**

Run: `git diff -- frontend/src/pages frontend/src/components frontend/src/styles/index.css`

Expected: no deep-feature removal and no role-specific copied common components.

### Task 16: Graph Memory white canvas and Inspector

**Files:**
- Modify: `frontend/src/components/graph-visualization.tsx`
- Modify: `frontend/src/components/graph-memory-view.tsx`
- Modify: `frontend/src/components/graph-path-inspector.tsx`
- Modify: `frontend/src/styles/memory-control.css`
- Test: `frontend/tests/graph-light-theme.test.tsx`

**Interfaces:**
- Consumes: existing bounded Graph view model.
- Produces: white/light SVG graph with typed nodes, neutral edges, teal selection, white Inspector.

- [ ] **Step 1: Write failing Graph semantics tests**

```tsx
it("test_graph_light_theme preserves accessible node selection", async () => {
  render(<GraphMemoryView data={demoGraphMemory} />);
  const node = screen.getByRole("button", { name: /新平路/ });
  await user.click(node);
  expect(node).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("heading", { name: "节点信息" })).toBeVisible();
});
```

- [ ] **Step 2: Run RED**

Run: `npm test -- tests/graph-light-theme.test.tsx tests/memory-control-plane.test.tsx`

Expected: FAIL on the target accessible Inspector/selection contract.

- [ ] **Step 3: Apply the limited light entity palette**

Use the exact entity colors from `docs/frontend_light_theme.md`, neutral edges, white/light canvas, and teal selected outline. Remove dark radial gradients, neon filters, and black node shadows. Preserve keyboard Enter/Space activation and bounded path rendering.

- [ ] **Step 4: Run GREEN**

Run: `npm test -- tests/graph-light-theme.test.tsx tests/memory-control-plane.test.tsx`

Expected: PASS.

- [ ] **Step 5: Inspect dark residuals**

Run: `rg -n "#0a1017|#101a23|rgba\(0,0,0|drop-shadow\(0 0" frontend/src/components/graph-* frontend/src/styles/memory-control.css`

Expected: no dark canvas/node/neon declarations remain.

### Task 17: Monitoring white operations UI

**Files:**
- Modify: `frontend/src/pages/monitor-page.tsx`
- Modify: `frontend/src/components/live-observability-panel.tsx`
- Modify: `frontend/src/components/observability-trend.tsx`
- Modify: `frontend/src/components/verified-baseline-panel.tsx`
- Modify: `frontend/src/styles/index.css`
- Test: `frontend/tests/monitoring-light-theme.test.tsx`

**Interfaces:**
- Consumes: existing typed observability summary/health and state machine.
- Produces: white operations view and external Grafana link.

- [ ] **Step 1: Write failing monitoring tests**

```tsx
it("test_monitoring_light_theme retains provenance and bounded colors", () => {
  renderMonitoring(liveObservabilityFixture);
  expect(screen.getByText("LIVE")).toBeVisible();
  expect(screen.getByRole("link", { name: "打开 Grafana" })).toHaveAttribute("target", "_blank");
});

it("keeps stale separate from live", () => {
  renderMonitoring(staleObservabilityFixture);
  expect(screen.getByText("STALE")).toBeVisible();
  expect(screen.getByText(/last safe samples/i)).toBeVisible();
});
```

- [ ] **Step 2: Run RED**

Run: `npm test -- tests/monitoring-light-theme.test.tsx`

Expected: FAIL on localized white-operations structure/provenance treatment.

- [ ] **Step 3: Migrate charts and operations sections**

Use white chart backgrounds, faint neutral grids, brand/semantic series, and non-color series distinction. Keep Grafana external. Preserve `LIVE`, `STALE`, `UNAVAILABLE`, `NO_PERMISSION`, verified-baseline, and `NOT EXPOSED` rules.

- [ ] **Step 4: Run GREEN and observability regressions**

Run: `npm test -- tests/monitoring-light-theme.test.tsx tests/monitoring-live.test.tsx tests/observability-client.test.ts`

Expected: PASS.

- [ ] **Step 5: Inspect diff checkpoint**

Run: `git diff -- frontend/src/pages/monitor-page.tsx frontend/src/components/live-observability-panel.tsx frontend/src/components/observability-trend.tsx frontend/src/components/verified-baseline-panel.tsx`

Expected: no Grafana imitation or rainbow palette.

### Task 18: Responsive, keyboard, contrast, and session-state regression

**Files:**
- Modify: `frontend/src/styles/index.css`
- Modify: `frontend/src/styles/memory-control.css`
- Test: `frontend/tests/accessibility-role-ui.test.tsx`
- Test: `frontend/tests/light-theme-contract.test.ts`

**Interfaces:**
- Produces: complete 1366/1440/1920 CSS behavior and automated accessibility contracts.

- [ ] **Step 1: Write failing keyboard/state tests**

```tsx
it("test_session_expired differs from forbidden", () => {
  renderProtected({ status: "expired", permissions: [] });
  expect(screen.getByRole("heading", { name: "会话已过期" })).toBeVisible();
  expect(screen.queryByRole("heading", { name: "无权访问" })).not.toBeInTheDocument();
});

it("status is not color-only", () => {
  render(<StatusBadge status="OFFLINE" />);
  expect(screen.getByText("离线")).toBeVisible();
});
```

- [ ] **Step 2: Run RED**

Run: `npm test -- tests/accessibility-role-ui.test.tsx tests/light-theme-contract.test.ts`

Expected: at least one new semantics/responsive source assertion fails.

- [ ] **Step 3: Complete breakpoints and interaction accessibility**

Implement documented Sidebar defaults, gutters, centered max width, table internal overflow, visible focus, tab keys, dialog behavior, reduced motion, and non-color status. Reassess the current `body min-width: 1100px` with browser proof; remove or narrowly scope it if it masks layout failure.

- [ ] **Step 4: Run GREEN and full frontend unit suite**

Run: `npm test`

Run: `npm run lint`

Run: `npm run build`

Expected: all PASS.

- [ ] **Step 5: Inspect dark values and source contracts**

Run: `rg -n "#080b10|#0a0e14|#0a1017|#0d121a|#101720|#101a23" frontend/src`

Expected: no migrated production surface uses the old dark backgrounds; any intentional historical/test string is documented.

### Task 19: Five-role Playwright QA and screenshot evidence

**Files:**
- Create: `frontend/e2e/role-based-light-ui.spec.ts`
- Create at run time: `docs/verification/frontend-role-ui/screenshots/*.png`
- Create at run time: `docs/verification/frontend-role-ui/browser-e2e.json`
- Create at run time: `docs/verification/frontend-role-ui/qa-results.md`

**Interfaces:**
- Consumes: real local/docker-dev frontend, server-issued or test-routed Principals, existing API stack.
- Produces: final browser proof for role distinction, authorization, light theme, responsive layout, and console health.

- [ ] **Step 1: Write failing role/browser scenarios**

The spec must assert:

```ts
await authenticatePage(page, "DISPATCHER");
await expect(page).toHaveURL(/\/workspace$/);
await expect(page.getByRole("link", { name: "系统监控" })).toHaveCount(0);
await expect(page.getByRole("button", { name: /强干预/ })).toHaveCount(0);

await authenticatePage(page, "OPERATOR");
await expect(page).toHaveURL(/\/operations$/);
await expect(page.getByRole("link", { name: "智能调度" })).toHaveCount(0);
```

Add Supervisor review/intervention, Auditor read-only, Admin full navigation, direct unauthorized route, expired session, Memory Graph selection, Monitoring states, and production-no-preview scenarios.

- [ ] **Step 2: Run RED against the pre-final implementation state**

Run: `npm run test:e2e -- role-based-light-ui.spec.ts`

Expected: FAIL until all role routes/light surfaces and environment setup are complete.

- [ ] **Step 3: Add computed light-theme and overflow assertions**

At 1366×768, 1440×900, and 1920×1080 assert Body/Sidebar/Topbar/Dialog/Table/Graph/Monitoring computed backgrounds are light and `document.documentElement.scrollWidth <= innerWidth` for main pages. Record console errors and page errors; expected arrays are empty.

- [ ] **Step 4: Capture the ten required screenshots**

Write exactly the filenames declared in the design spec. Screenshots are QA evidence, not concept designs, and are created only after implementation authorization.

- [ ] **Step 5: Run GREEN and existing browser regressions**

Run: `npm run test:e2e -- role-based-light-ui.spec.ts security-auth.spec.ts observability-live.spec.ts`

Expected: all selected specs PASS, console/page error arrays empty, all three viewports non-overflowing.

- [ ] **Step 6: Inspect evidence checkpoint**

Run: `Get-ChildItem -LiteralPath '..\docs\verification\frontend-role-ui\screenshots' | Select-Object Name,Length`

Expected: the ten named non-empty PNG files only.

### Task 20: Performance, full regression, and final acceptance

**Files:**
- Modify only if results require factual updates: `docs/verification/frontend-role-ui/qa-results.md`
- No production changes are permitted during the final evidence step without returning to the relevant RED/GREEN task.

**Interfaces:**
- Produces: complete acceptance evidence and a clean design-to-implementation trace.

- [ ] **Step 1: Record pre/post production bundle sizes**

Run before and after approved implementation: `npm run build`

Record Vite asset names and byte sizes. Expected: no unexplained material bundle increase and no large UI/graph framework.

- [ ] **Step 2: Run required frontend gates**

Run: `npm run lint`

Run: `npm test`

Run: `npm run build`

Expected: PASS.

- [ ] **Step 3: Run repository gates required by AGENTS.md**

Run from workspace root: `ruff check backend`

Run from workspace root: `pytest`

Run the targeted Docker/security/observability integrations applicable to changed frontend contracts using the existing scripts. Expected: PASS; report real skips separately and do not claim unrun runtime coverage.

- [ ] **Step 4: Run final source/security scans**

Run: `rg -n "VITE_.*SECRET|Authorization:|Bearer [A-Za-z0-9]|DEVELOPMENT_JWT_SECRET" frontend docs/verification/frontend-role-ui`

Expected: no committed/generated secret or token material.

Run: `rg -n "#080b10|#0a0e14|#0a1017|#0d121a|#101720|#101a23" frontend/src`

Expected: no old dark production surface.

- [ ] **Step 5: Run whitespace and final diff checks**

Run: `git -c safe.directory="C:/Users/24090/OneDrive/Desktop/县域物流识别异常" diff --check`

Run: `git status --short`

Expected: `diff --check` has no output. Status contains only intended implementation/evidence changes plus pre-existing user work, which must remain identifiable and untouched.

- [ ] **Step 6: Complete the A–K self-review in the verification report**

Record explicit PASS/FAIL evidence for Dispatcher Monitoring, Dispatcher Override, Supervisor Review/Intervention, Operator landing, Auditor writes, Admin debug dump, true-white background, light Sidebar, light Graph/Monitoring, shared composition, and production role switch.

- [ ] **Step 7: Human approval gate**

Stop after reporting actual commands/results. Do not merge, deploy, or commit without separate user authorization.

## Plan self-review

- Spec coverage: Tasks 1–6 cover Principal, landing, navigation, Shell, identity, and production preview boundary. Tasks 7–14 cover shared states and five distinct role workspaces. Tasks 15–17 preserve/migrate existing deep features, Graph, and Monitoring. Tasks 18–20 cover accessibility, responsive, browser QA, performance, security, and final verification.
- Data-truth coverage: Tasks 8–10 explicitly prohibit Mock fallback and remove current API-mode fixture KPIs. Backend gaps remain `NOT EXPOSED` until separately approved.
- Security coverage: Tasks 2, 5, 6, 12, 14, 18, and 19 verify permission-first navigation, direct route enforcement, production preview exclusion, high-risk action gates, and read-only audit.
- Type consistency: `RoleLanding`, `NavigationItem`, `NavigationGroup`, `DataProvenance`, and `ReadState<T>` are introduced before consumers.
- No placeholder implementation instructions are used; absent backend contracts are deliberate product states with explicit enablement gates, not deferred fake implementations.
