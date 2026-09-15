# CountyFlow Neon Dashboard Visual Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将用户确认的十张深蓝科技运营界面重构为 CountyFlow 可运行、可交互、连接现有后端与真实高德地图的统一前端。

**Architecture:** 保留现有 React 路由、权限、API hooks、车辆状态机和高德地图适配器，仅增加共享视觉外壳、页面横幅、数据卡与图表/表格主题。各业务页面继续消费已有真实接口；缺少接口的展示指标只在既有 mock 模式下出现并标注数据来源。

**Tech Stack:** React, TypeScript, React Router, CSS, lucide-react, AMap JS API, Vitest, Playwright

**Spec:** `docs/superpowers/specs/2026-09-10-vehicle-rescue-maintenance-map-system-design.md`

## Global Constraints

- 不硬编码、提交、返回或记录任何 API 密钥。
- 高德地图保留自由拖动、道路吸附、真实路线和离线回退。
- 车辆故障、救援、维修和复岗状态只来自后端事实，不由视觉倒计时伪造。
- 1440×900 不裁切，686px 宽不产生横向溢出，并支持 `prefers-reduced-motion`。
- 每个行为变化先写失败测试，再做最小实现并执行相关回归。

---

### Task 1: Shared night operations shell

**Files:**
- Modify: `frontend/src/components/app-shell.tsx`
- Create: `frontend/src/styles/countyflow-night.css`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/tests/app-shell-light.test.ts`
- Modify: `frontend/e2e/role-based-light-ui.spec.ts`

**Interfaces:**
- Consumes: `useLocation`, `useBackendHealth`, existing role navigation and auth switcher.
- Produces: `data-surface="page-hero"`, route-based title/subtitle/tags, reusable night tokens.

- [ ] **Step 1: Write the failing shell contract**

  Assert that the final theme defines `--background: #020b1c`, dark sidebar/topbar surfaces, and that `AppShell` renders a route-aware `data-surface="page-hero"` region.

- [ ] **Step 2: Run the focused test and verify RED**

  Run: `npm test -- app-shell-light.test.ts`
  Expected: FAIL because the current shell still declares semantic white surfaces and has no page hero.

- [ ] **Step 3: Implement the shared visual shell**

  Add a route presentation map, a compact status topbar, the reusable logistics hero, dark tokens, neon focus states, responsive behavior, and a real raster hero background.

- [ ] **Step 4: Run focused tests and verify GREEN**

  Run: `npm test -- app-shell-light.test.ts role-navigation.test.ts responsive-accessibility.test.ts`
  Expected: PASS.

### Task 2: Login fidelity and motion

**Files:**
- Modify: `frontend/src/pages/login/login-page.tsx`
- Modify: `frontend/src/pages/login/login-hero.tsx`
- Modify: `frontend/src/pages/login/login-card.tsx`
- Modify: `frontend/src/styles/login.css`
- Modify: `frontend/tests/login-page.test.tsx`

**Interfaces:**
- Consumes: existing demo employee login callback and prefilled password behavior.
- Produces: selected-account login, cinematic road motion, responsive glass panel, reduced-motion fallback.

- [ ] **Step 1: Add a failing login visual/behavior contract**

  Assert the background image, route layer, vehicle layer, account selector, read-only password and reduced-motion-safe hooks remain present.

- [ ] **Step 2: Run and verify RED for the new fidelity marker**

  Run: `npm test -- login-page.test.tsx`
  Expected: FAIL for the missing selected visual marker.

- [ ] **Step 3: Implement the selected reference layout without changing authentication semantics**

- [ ] **Step 4: Run login unit and Playwright tests**

  Run: `npm test -- login-page.test.tsx`
  Run: `npx playwright test e2e/login-page.spec.ts`
  Expected: PASS.

### Task 3: Fleet command map

**Files:**
- Modify: `frontend/src/pages/fleet-live-map-page.tsx`
- Modify: `frontend/src/components/amap-fleet-map.tsx`
- Modify: `frontend/src/components/vehicle-command-center.tsx`
- Modify: `frontend/src/styles/fleet-command-map-v3.css`
- Modify: `frontend/src/styles/vehicle-command-center.css`
- Modify: `frontend/tests/fleet-live-map-page.test.tsx`
- Modify: `frontend/tests/amap-fleet-map.test.tsx`

**Interfaces:**
- Consumes: `MapSnapshot`, AMap loader, vehicle operation snapshot.
- Produces: dark base-map presentation, live layer controls, vehicle detail, anomaly overlay, fast loading skeleton.

- [ ] **Step 1: Add failing tests for retained AMap, selected vehicle and loading state**
- [ ] **Step 2: Run focused tests and verify RED**
- [ ] **Step 3: Implement the visual composition while retaining map interactions and route truth**
- [ ] **Step 4: Run fleet unit and E2E tests and verify GREEN**

### Task 4: Business workflow pages

**Files:**
- Modify: `frontend/src/pages/dispatch-task-center-page.tsx`
- Modify: `frontend/src/pages/orders-page.tsx`
- Modify: `frontend/src/pages/reviews-page.tsx`
- Modify: relevant files under `frontend/src/components/workspace/`
- Modify: corresponding tests under `frontend/tests/`

**Interfaces:**
- Consumes: existing dispatch, order and review read/command services.
- Produces: screenshot-aligned cards, filters, tables, details and decision controls with unchanged permissions.

- [ ] **Step 1: Add one failing behavior contract per page**
- [ ] **Step 2: Run each contract and verify RED**
- [ ] **Step 3: Implement shared cards/tables and page-specific layouts**
- [ ] **Step 4: Run business-page unit and role tests and verify GREEN**

### Task 5: AI, memory and operations pages

**Files:**
- Modify: `frontend/src/pages/agents-page.tsx`
- Modify: `frontend/src/pages/memory-page.tsx`
- Modify: `frontend/src/pages/runtime-page.tsx`
- Modify: `frontend/src/pages/monitor-page.tsx`
- Modify: related visualization components and tests.

**Interfaces:**
- Consumes: existing agent events, memory records, runtime and observability hooks.
- Produces: orchestration view, knowledge graph, runtime health and monitoring dashboard consistent with the visual references.

- [ ] **Step 1: Add failing source-truth and interaction contracts**
- [ ] **Step 2: Run focused tests and verify RED**
- [ ] **Step 3: Implement each page using shared night components**
- [ ] **Step 4: Run focused tests and verify GREEN**

### Task 6: Visual QA, accessibility and regression

**Files:**
- Create: `design-qa.md`
- Modify: visual CSS/components only when QA identifies P0-P2 issues.

**Interfaces:**
- Consumes: selected reference screenshots and same-viewport browser captures.
- Produces: `design-qa.md` with `final result: passed` and verified local preview.

- [ ] **Step 1: Run frontend lint, unit tests and build**
- [ ] **Step 2: Run targeted Playwright flows for login, fleet map, roles and vehicle lifecycle**
- [ ] **Step 3: Capture the reference and implementation at matching viewport states**
- [ ] **Step 4: Fix all P0-P2 visual differences and repeat comparison**
- [ ] **Step 5: Run `git -c safe.directory=<workspace> diff --check` and record actual output**
