# CountyFlow V2-F2 Role-Based Light Frontend Design

**Status:** DESIGN READY — awaiting approval for TDD implementation

**Date:** 2026-08-29

**Scope:** current frontend audit, UX/information architecture, light design system, security integration, migration strategy, and implementation plan. No production frontend/backend code, image, Figma artifact, new business capability, Git commit, or security-design change is included.

## 1. Executive decision

Select **Option A: Single SPA + Role-Based App Shell + Permission-Driven Navigation + Role Landing Pages**.

CountyFlow keeps the existing React/Vite/router/API patterns. The authenticated Principal resolves a role-oriented landing and a permission-filtered navigation. Five role experiences are composed from shared workbench modules, not five copied applications. Frontend permissions improve UX; backend permission enforcement remains the security boundary.

The visual system moves completely from the current blue-black console to a true white enterprise operations UI. Main, Sidebar, Topbar, tables, dialogs, Graph, and in-app Monitoring all migrate together through tokens and shared primitives.

## 2. Audit method and evidence

The audit read the complete `frontend/src`, current tests/E2E, API clients, backend route declarations, `docs/permissions.md`, V2-F/G1/G2 design and verification evidence, and current repository status. There are no Git commits in the repository; the working tree already contains extensive user-owned staged/untracked work, which remains untouched.

The running frontend was inspected with Playwright because the Browser plugin is not installed in this session. The exact configured origin `http://localhost:5173` was used against a responding backend. Pages were checked at 1440×900 and the shell at 1366×768. The flow covered page identity, meaningful DOM, framework overlay absence, computed backgrounds, overflow, Memory tab interaction, Sidebar collapse, and five role identities. No screenshots were saved because this round prohibits design images. A deliberate missing-task route produced expected 404 console entries; other inspected product routes rendered without a framework error overlay.

Observed computed backgrounds:

- Body/App Shell: `rgb(8, 11, 16)` (`#080b10`)
- Sidebar: `rgb(10, 14, 20)` (`#0a0e14`)
- Topbar: `rgba(8, 11, 16, 0.82)`
- Graph canvas: `rgb(10, 16, 23)` (`#0a1017`)

At 1366×768, the current shell did not overflow horizontally, but `body` has a hard-coded `min-width: 1100px`. Sidebar collapse works. All five roles currently receive the same seven navigation items. Dispatcher/Supervisor/Admin land on the same `/` dashboard; Operator/Auditor land on `/` and immediately see “无权访问”.

## 3. Existing frontend inventory

### 3.1 Routes and pages

| Current route | Page/component | Exists | Permission guard | Product status |
|---|---|:---:|---|---|
| `/` | `DashboardPage` | yes | `dispatch:read` | capability summary; role-neutral; API business summary not exposed |
| `/anomalies` | `AnomaliesPage` | yes | `anomalies:read` | Mock records only; API page currently shows static KPI copy with zero rows |
| `/dispatch` | `DispatchStartPage` | yes | `dispatch:create` | real async API submit, but only a fixed rain-case button, not a product form |
| `/dispatch/:taskId` | `DispatchDetailPage` / `ApiDispatchDetailPage` | yes | `dispatch:read` | real task status/result/WebSocket; Runtime workbench embedded |
| `/orders` | `OrdersPage` | yes | `orders:read` | Mock records only; API page currently shows static KPI copy with zero rows |
| `/agents` | `AgentsPage` | yes | `agents:read` | eight-agent live task-event inspector or Demo data |
| `/memory` | `MemoryPage` | yes | `memory:read` | Vector/Graph/Shared tabs; mutation action intentionally not open |
| `/monitor` | `MonitorPage` | yes | `monitor:read` | real observability summary/health plus verified baseline |

`PlaceholderPage` exists as a component but is not routed. Runtime Thread, Checkpoint, Intervention, Override History, Capacity, Routing, and Audit Evidence exist as components embedded in dispatch detail. There is no top-level Workspace, Supervisor, Operations, Runtime list, Review Queue, Audit Center, or Admin Overview page.

### 3.2 Shell, navigation, and permissions

- `AppShell` owns a dark fixed Sidebar/Topbar and static seven-item `navItems` array.
- Navigation is not filtered by Principal, so forbidden links remain visible and lead to a 403 surface.
- Router-level `RequirePermission` guards every existing page.
- `PermissionGate` distinguishes anonymous/expired and forbidden states; API mode never treats Mock as authorization.
- `RuntimeWorkbench` gates read/override behavior with `runtime:read` and `runtime:override`.
- `SharedMemoryControl` checks `memory:mutate`, but the current write button remains disabled and no mutation form is exposed.
- Current Topbar shows a generic `管` avatar rather than the authenticated person's role identity.

### 3.3 Current data-source audit

| Surface | API mode truth | Mock / verified content | Audit result |
|---|---|---|---|
| Dashboard | no business summary endpoint; explicit `业务汇总接口未暴露` | V2 capability/acceptance evidence | boundary is explicit; not role-specific |
| Anomalies | no list API | records and all KPI values are local fixtures | gap: static KPI values still render in API mode; must not survive V2-F2 |
| Dispatch create | `POST /api/v1/dispatch-tasks` | Mock adapter in Mock mode | real path exists; form is fixed to one sample payload |
| Dispatch detail | status/result APIs + ticketed WebSocket | Mock detail in Mock mode | strongest current live business surface |
| Orders | no list API | records and all KPI values are local fixtures | gap: static KPI values still render in API mode; must not survive V2-F2 |
| Agents | task-scoped WebSocket events | Demo agent specifications | no aggregate live agent worklist; task ID is required |
| Vector Memory | no browse API | verified Top-1/Top-3 evidence | correctly renders `NOT EXPOSED` in API mode |
| Graph Memory | task-scoped WebSocket Graph events | Demo bounded graph | live when a task ID is supplied; no global graph browser API |
| Shared Memory | `GET /api/v1/memory/facts/{fact_key}` | Demo fact in Mock mode | real fact lookup and history; no current write form |
| Runtime/Override | thread/intervention/override/history APIs | Mock workbench in Mock mode | real, permission-gated, task-context only |
| Monitoring | `/health` + `/observability/summary` | verified V2-E baseline | live/stale/not-exposed semantics exist; page is dark |
| Audit | dispatch event/result evidence in detail; security audit API exists | no Audit Center fixture needed in API mode | frontend client/page for security audit is missing; no unified business audit feed |

The frontend currently has 10 page files, 26 component files, 21 unit-test files, and 12 Playwright specs. The current repository evidence reports V2-G2 as complete with 688 backend tests (7 opt-in skips) and 91 frontend tests at that acceptance point; these are historical current-branch artifacts, not results rerun in this design-only round.

## 4. Architecture options

### Option A — one SPA, role-composed shell (selected)

- One router, API layer, design system, and test surface.
- Canonical navigation registry filtered by permissions and ordered by role context.
- Role-specific landing compositions reuse shared modules.
- Preserves current URLs while adding role homes.
- Lowest maintenance and bundle risk; cleanly attaches to G2 Principal.

### Option B — separate Dispatcher and Admin frontends (rejected)

- Clear deployment separation, but duplicates components, API clients, styles, tests, and security integration.
- Supervisor/Operator/Auditor still create ambiguous splits.
- Experiences drift and bundle/maintenance costs increase.

### Option C — keep one all-purpose console and hide a few buttons (rejected)

- Smallest code change, but retains the current technical-console mental model.
- Fails the role landing, navigation, Operator, Auditor, and Supervisor acceptance criteria.
- Treats role UX as subtraction rather than a different work focus.

## 5. Selected frontend architecture

```text
AuthProvider / session store
  → PrincipalAdapter
      roles: Role[]
      permissions: Set<Permission>
  → RoleLandingResolver
  → NavigationResolver(canonical registry, role context, permissions)
  → AppShell
      RoleNavigation
      Topbar identity
      route outlet
  → Role landing composition
      shared modules + per-module PermissionGate
  → existing API clients / new narrow read clients
  → FastAPI authorization and resource policy
```

### Proposed frontend boundaries

- `auth/`: Principal/session and permission checks only.
- `navigation/`: canonical registry, visibility resolution, landing resolution; no API calls.
- `layouts/`: App Shell and shared responsive workspace layout.
- `workspaces/`: thin role landing compositions.
- `components/ui/`: theme-backed primitives and complete interaction states.
- `components/workspace/`: shared domain-neutral modules such as TaskQueue and SystemHealth.
- `services/api/`: narrow typed clients; never Mock fallback in API mode.
- `styles/tokens.css`: semantic tokens; page styles consume tokens rather than hard-coded colors.

Role strings do not scatter through page JSX. A role may alter ordering/presentation, while all routes and actions resolve from permissions.

## 6. Role architecture and workspaces

Detailed personas, flows, landing pages, navigation groups, Page × Role matrix, and route/permission mapping are normative in [frontend_role_ux.md](../../frontend_role_ux.md).

### Dispatcher

Default `/workspace`: truthful work overview, prioritized My Tasks, current dispatches, AI recommendations, recent completion. Primary navigation is business-only. Agent/Memory evidence is summarized inside the decision flow. Monitoring and Runtime Override are absent.

### Supervisor

Default `/supervisor`: risk summary, Review Queue, intervention-needed tasks, team state, and Override History. It reuses Dispatcher business pages but adds review and intervention action rails by permission. The Danger Zone remains backend-eligibility-driven.

### Operator

Default `/operations`: live observability, workers/streams/dependencies, Runtime summaries, and necessary audit. It contains no dispatch creation, review, Runtime Override, or Memory mutation action.

### Auditor

Default `/audit`: immutable evidence timelines for dispatch, Runtime/Override, Memory mutation, and security events. All actions are read-only; forbidden writes are absent rather than disabled.

### Admin

Default `/overview`: productized summaries and links across business, AI, Memory, Runtime, Observability, and Governance. It is not a debug dump and adds no IAM console.

## 7. Permission-driven navigation and landing

`NavigationItem` contains id, localized label, icon, route, group, required permissions, and primary/contextual visibility. The registry is filtered by Principal permissions before rendering. Role composition then orders remaining items. Direct URL navigation still hits `RequirePermission`.

`/` redirects through `RoleLandingResolver`. Current-contract multi-role priority is `ADMIN → SUPERVISOR → OPERATOR → AUDITOR → DISPATCHER`; it chooses presentation only. Production has no self-service role switch. Local/docker-dev/test may request a server-issued development identity through an explicitly marked `DEV AUTH` preview.

The design aligns to `docs/permissions.md`:

- Dispatcher lacks `monitor:read`, `runtime:read`, `runtime:override`, `memory:mutate`, and `audit:read`.
- Supervisor has business review, Runtime read/override, Memory mutation, audit, and monitoring.
- Operator has agent/runtime/audit/monitor reads only.
- Auditor has memory/runtime/audit/monitor reads only.
- Admin receives every explicit permission plus `system:admin`; `system:admin` is not a wildcard in endpoint code.

## 8. Runtime intervention UX

The Supervisor/Admin route first reads backend intervention eligibility. `runtime:read` displays state and history; `runtime:override` displays the final action. The white Danger Zone includes entity/field, old/new value, reason, expected state version, expected next node, downstream effect, idempotency/loading state, and high-risk confirmation. It preserves current 409 stale-state, forbidden, terminal, concurrent, unavailable, and applied semantics. No frontend equality check or local state override is introduced.

## 9. White enterprise theme

The normative token, component, Graph, chart, responsive, and accessibility specification is [frontend_light_theme.md](../../frontend_light_theme.md).

Key decisions:

- Main background is exactly `#FFFFFF`.
- Sidebar and Topbar are white with neutral borders.
- Teal `#0F766E` is the restrained brand action/selection/focus color.
- Text is dark neutral; normal text never uses decorative low-contrast gray.
- Cards are white, subtle-border, usually shadowless.
- Tables use light-neutral headers, white rows, horizontal dividers, subtle hover/selection.
- Graph canvas and Node Inspector are white/light-neutral with limited soft entity colors.
- In-app Monitoring is a white operations UI; Grafana remains external.

## 10. State and data-truth strategy

Common state components distinguish:

1. business empty;
2. skeleton loading;
3. `NOT EXPOSED` read contract;
4. API failure/retry;
5. 403 forbidden;
6. expired session;
7. system unavailable;
8. stale last-known telemetry.

Provenance values remain `LIVE`, `DEMO`, `VERIFIED`, `STALE`, `NOT EXPOSED`. Dispatcher pages use natural-language state copy and minimize technical badges. Operator/Admin/evidence Inspectors show badges where provenance is material. API mode never falls back to Mock and never renders fixture KPIs as live zeros.

## 11. Minimal backend read-model gaps

These are recorded dependencies, not implementation authorization:

| UX need | Current evidence | Minimal gap | Permission |
|---|---|---|---|
| My Tasks / Dispatcher counts | task GET only by ID; `DispatchTask` has no actor/owner column | durable task actor/owner attribution plus bounded actor-filtered task list/summary | `dispatch:read` |
| Anomaly Center live list/counts | no anomaly list endpoint | paged safe anomaly read projection with filters/counts | `anomalies:read` |
| Orders live list/counts | no order list endpoint | paged safe order read projection with risk/anomaly relation | `orders:read` |
| Supervisor team queue | no task list/owner projection | bounded team task list and wait/risk fields | `dispatch:review` |
| Review Queue + confirm/reject | permission exists; no review endpoint/action | review read projection and explicit idempotent review action contract | `dispatch:review` |
| Global Runtime Threads | current reads require task/thread ID | bounded thread list/summary; raw checkpoint remains prohibited | `runtime:read` |
| Unified Audit Center | security audit list exists; business audit is task-scoped | bounded cross-domain audit projection or explicit federated read contracts | `audit:read` |
| Admin business health | current dashboard says summary not exposed | bounded product summary derived from real read models | concrete constituent permissions; not implicit wildcard |
| Security Summary | security audit exists, no frontend summary client | typed security health/summary projection only if approved by G2 | `monitor:read` and/or `audit:read` per field |
| Interactive Dev Role Preview | current development-session endpoint always issues `ADMIN` and accepts no role selector | allowlisted local/docker-dev-only server-issued role preview contract, or keep UI preview unavailable | development profile only; never production |

The implementation must not invent live ownership, review transitions, or KPI values before these contracts exist. Pages may ship their shell and truthful `NOT EXPOSED` state behind the approved phase plan.

## 12. V2-G2 dependency boundary

### READY NOW in the current repository

- `AuthenticatedPrincipal` fields: subject, display name, roles, permissions, auth method, issued/expiry times.
- Canonical five roles and closed permission enum.
- Server-owned role-to-permission mapping.
- Development JWT and OIDC JWT authentication paths.
- Frontend session store/AuthProvider and authenticated API client.
- Route-level PermissionGate and action-level permission hooks.
- 401/403 separation, session expiry, logout/revocation behavior.
- Backend protection for dispatch, Runtime, Memory, Observability, security audit, and WebSocket tickets.
- G2 verification artifact reports complete role/browser/security coverage.

### REQUIRES V2-F2 IMPLEMENTATION, not G2 redesign

- Principal adapter with localized role identity.
- RoleLandingResolver and permission-filtered canonical navigation.
- Role landing compositions and production-hidden development preview.
- Security audit frontend client/page and permission-aware UI actions.
- Tests that navigation does not expose forbidden items.

### REQUIRES A SEPARATELY APPROVED G2 DEVELOPMENT-ONLY FOLLOW-UP

- Interactive local/docker-dev Role Preview is not currently supported by the real issuer: `DevelopmentSessionIssuer.issue_admin()` always returns `ADMIN`, and `POST /api/v1/auth/development-session` has no role input.
- A future preview must use an allowlisted non-production server contract and return a server-built Principal. Frontend-generated role/permission claims are prohibited.
- Automated Playwright role tests may continue routing test Principals. That test mechanism is evidence, not a production or docker-dev role-switch implementation.

### REQUIRES MINIMAL BACKEND READ CONTRACTS

The gaps in section 11 require separately approved read-model work. They do not require changing the G2 security design. Every new endpoint must be registered once in the backend endpoint-permission contract and use existing Principal/permission/resource admission.

There is no current design blocker in the G2 authentication/permission foundation. Production deployment must still supply correct OIDC configuration and must never enable the development role preview.

## 13. Responsive and accessibility acceptance

- 1366×768, 1440×900, and 1920×1080 are required browser viewports.
- 1366 may start with collapsed Sidebar; 1440+ starts expanded.
- Large desktop content centers/expands up to about 1680px instead of clustering upper-left.
- No main-page horizontal overflow; dense tables may have bounded internal scrolling.
- WCAG 2.2 AA contrast, keyboard navigation, visible focus, dialog containment, tab semantics, accessible table actions, and non-color status cues are required.
- Motion is limited to 150–200ms and honors reduced motion.

## 14. Migration phases

1. **Theme Tokens + Common UI** — introduce semantic tokens and primitive behavior tests; no page-by-page hard-coded replacement.
2. **Light App Shell** — convert Body/Main/Sidebar/Topbar/overlay/dialog foundation as one coherent shell.
3. **Role/Permission Navigation** — canonical registry, landing resolver, permission filters, dev-only preview.
4. **Dispatcher Workspace** — work overview, My Tasks and dispatch flow with truthful missing-contract states.
5. **Supervisor Workspace** — Review Queue shell, supervisor risk composition, Runtime Intervention and history placement.
6. **Operator/Auditor/Admin** — distinct landing compositions using live existing reads and explicit gaps.
7. **Existing Pages Light Migration** — Anomalies, Dispatch, Orders, Agents, Memory, Runtime, Monitoring, Audit evidence.
8. **Responsive / Accessibility** — three desktop viewports, contrast, keyboard, focus, reduced motion.
9. **Browser E2E / Regression** — five identities, direct route authorization, deep workflows, screenshot evidence, bundle comparison.

Each phase is independently testable and ends with diff inspection. A half-light shell or dark Graph/Monitoring residual is not releasable.

## 15. Test plan

Future implementation follows behavior-level TDD with observed RED before the smallest GREEN. Required named coverage:

- `test_dispatcher_navigation`
- `test_dispatcher_default_workspace`
- `test_dispatcher_no_runtime_override`
- `test_supervisor_review_visible`
- `test_supervisor_runtime_override_visible`
- `test_operator_monitoring_default`
- `test_operator_no_dispatch_write`
- `test_auditor_read_only`
- `test_admin_full_navigation`
- `test_permission_driven_navigation`
- `test_multi_role_permissions`
- `test_production_no_role_switcher`
- `test_dev_role_preview_marked`
- `test_light_theme_app_shell`
- `test_light_theme_sidebar`
- `test_light_theme_table`
- `test_graph_light_theme`
- `test_monitoring_light_theme`
- `test_unauthorized_route`
- `test_session_expired`
- `test_api_mode_no_fake_role_data`

Add accessibility tests for navigation, tabs, table actions, dialog focus, status semantics, and axe violations. Retain existing Runtime Override, Graph/Memory, WebSocket, authenticated role, and Observability regressions. Compare production bundle output to the pre-V2-F2 baseline; do not add a large UI or graph framework.

## 16. Browser QA plan

Formal implementation uses real browser verification, not concept images. For every identity, verify page identity, meaningful DOM, no framework overlay, console health, interaction state change, authorization on direct routes, session expiry, and truthful API state.

Required screenshot evidence, produced only during approved implementation, is stored under `docs/verification/frontend-role-ui/screenshots/`:

- `dispatcher-workspace.png`
- `dispatcher-anomaly.png`
- `dispatcher-dispatch.png`
- `supervisor-workspace.png`
- `supervisor-intervention.png`
- `operator-operations.png`
- `auditor-audit.png`
- `admin-overview.png`
- `memory-light.png`
- `monitoring-light.png`

QA also checks computed Body/Sidebar/Topbar/Dialog/Table/Graph/Monitoring backgrounds to reject dark residues, and runs at 1366×768, 1440×900, and 1920×1080.

## 17. Design scan and acceptance rules

Automated source/computed-style scans reject:

- the existing dark shell values and known dark Graph/Memory values on migrated surfaces;
- Sidebar or dialog computed backgrounds below the approved light threshold;
- fixture KPI strings rendered in API mode without `DEMO`/`VERIFIED` scope;
- navigation items lacking a permission declaration;
- production builds containing the development role-preview control;
- five copied landing implementations with materially duplicated JSX.

The scan complements, but does not replace, browser inspection and accessibility checks.

## 18. Self-review

| Check | Result | Evidence in design |
|---|---|---|
| A. Dispatcher sees Monitoring? | PASS — no | hidden in role matrix; lacks `monitor:read` |
| B. Dispatcher can Override? | PASS — no | hidden; lacks `runtime:override` |
| C. Supervisor has Review + Intervention? | PASS | dedicated queue flow plus backend-driven Danger Zone/history |
| D. Operator still looks like Dispatcher? | PASS — no | `/operations` is default and has no dispatch CTA |
| E. Auditor has write actions? | PASS — none | all Auditor cells are read/visible/hidden; write affordances absent |
| F. Admin is a debug dump? | PASS — no | product summaries and progressive Inspectors; raw internals prohibited |
| G. Background truly white? | PASS | `--background: #FFFFFF` hard rule |
| H. Sidebar still dark? | PASS — no | white Sidebar with neutral border |
| I. Graph/Monitoring black? | PASS — no | light Graph canvas and white operations charts |
| J. Five frontend copies? | PASS — no | thin compositions over shared modules |
| K. Production self-service role switch? | PASS — none | preview is development JWT only and removed from production |

## 19. Files produced by this design round

- `docs/frontend_role_ux.md`
- `docs/frontend_light_theme.md`
- `docs/superpowers/specs/2026-08-29-v2-f2-role-based-light-frontend-design.md`
- `docs/superpowers/plans/2026-08-29-v2-f2-role-based-light-frontend.md`

No production frontend file is modified. No image is generated. No Git commit is created.
