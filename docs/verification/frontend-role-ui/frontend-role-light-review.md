# V2-F2 Role UI light-theme QA ledger

**Review date:** 2026-08-29  
**Scope:** the implemented CountyFlow React SPA, five server-issued development roles, and the white enterprise theme.  
**Evidence source:** real Playwright browser runs against the Docker backend and data stores. The Browser plugin was unavailable, so the project Playwright runner was used as the approved browser fallback. No concept images or ImageGen assets are evidence.

## Acceptance summary

- The same SPA resolves `AuthenticatedPrincipal → permissions → role landing → permission-filtered canonical navigation`.
- FastAPI remains the authorization boundary. Frontend hiding and route guards are UX only.
- Development role preview calls `POST /api/v1/auth/development-session`; it does not construct permissions in the browser.
- Production compilation removes the role preview branch, while the backend production profile rejects the development-session route.
- API mode shows real responses or explicit `EMPTY`, `NOT EXPOSED`, `UNAVAILABLE`, or `NO PERMISSION` states. It does not fall back to static business KPIs.
- Computed browser colors for `body`, `.app-shell`, `.sidebar`, `.topbar`, and the Runtime Intervention dialog are `rgb(255, 255, 255)`.
- Graph canvas is `rgb(246, 248, 250)` or white; its inspector and Monitoring panel are white.
- Browser viewports 1366×768, 1440×900, and 1920×1080 have no document-level horizontal overflow.
- The observed Monitoring state was honestly `STALE`: the Prometheus backend target was up, but at least one fixed query group had no current sample. The UI displayed the last-safe-sample warning rather than claiming `LIVE`.

## Page-by-page review

| Page / evidence | Before problem | Implemented change | Role behavior | Theme evidence | Data truth | Responsive evidence | Remaining intentional gap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Dev identity — `role-preview-dev.png` | Docker development always entered Admin, so other workspaces could not be exercised interactively. | Added a visibly labelled `DEV AUTH` selector backed by a server-issued session. | Five allowlisted roles land at their role resolver target; the client cannot submit permissions. | White Topbar, select, focus, and identity block. | Principal, role, and permissions come from the backend response. | Included in 1440 capture; selector remains inside the Topbar at 1366. | Production OIDC login remains outside V2-F2. |
| Dispatcher workspace — `dispatcher-workspace.png` | The common technical console did not foreground dispatch work. | Added queue, risk, recent-running, recommendation, and eight-stage workflow composition. | Dispatcher sees business navigation and no Monitoring or Runtime Override entry. | White workspace, restrained teal active state, light sections and tables. | Missing aggregate/list contracts show explicit `NOT EXPOSED`; no fabricated counts. | Priority work remains first and sections reflow at desktop breakpoints. | “My Tasks” and aggregate business summary APIs are not exposed. |
| Anomaly center — `dispatcher-anomaly.png` | Static KPI cards contradicted a real empty/API-unavailable result. | Removed API-mode static KPIs and added a contract-specific state. | Dispatcher retains permitted refresh/dispatch path only. | Light table/empty-state surface. | Displays “异常列表接口尚未开放”; no demo fallback. | No page-level overflow at all required viewports. | Anomaly list/summary read API is not exposed. |
| Smart dispatch — `dispatcher-dispatch.png` | The form used a large undifferentiated panel. | Organized required context, collapsible advanced inputs, task stream, and localized agent stages. | Dispatcher can submit; unauthorized roles do not receive the business write entry. | White form controls with borders, teal focus, and light execution panels. | Submission and task events remain real API/WebSocket data. | Form and task sections stack cleanly at 1366. | Global recent-dispatch list projection is not exposed. |
| Supervisor workspace — `supervisor-workspace.png` | No distinct review/risk landing page existed. | Added review, risk, intervention, override, and result-summary composition. | Supervisor receives review and Runtime navigation based on permissions. | White enterprise summary and explicit provenance states. | Review Queue and global intervention list are `NOT EXPOSED`, never local arrays. | Queue schema and risk sections reflow without document overflow. | Unified review queue and global intervention list APIs are not exposed. |
| Runtime Intervention — `supervisor-intervention.png` | The former dark modal did not fit the light system. | Migrated the dialog while retaining danger hierarchy, confirmation, and focus containment. | Supervisor completed a real legal override to `APPLIED`; Dispatcher direct API returned 403. | Computed dialog background is white; neutral overlay plus danger title, warning, border, and final action remain prominent. | Eligibility, checkpoint version, expected node, and result come from the real runtime API. | Focused 1440×900 viewport evidence keeps the full dialog usable. | No global intervention task list projection; known task/thread navigation remains supported. |
| Operator workspace — `operator-operations.png` | Operations work was mixed with business actions. | Added monitor-first health, worker, dependency, stream, runtime, and recovery composition. | Operator has no dispatch creation, review, override, or Memory mutation controls. | Light health surfaces, semantic states, and white operational tables. | Health details distinguish configured, unavailable, and not-exposed values. | Dense operations sections wrap at desktop breakpoints. | Worker consumer detail is not exposed by the current health DTO. |
| Auditor workspace — `auditor-audit.png` | Audit evidence was not a dedicated read-only product surface. | Added a live bounded Security Audit timeline and evidence-scope states. | Auditor page contains no buttons or mutation action. | White table, light header, skeleton, empty, and failure states. | Reads `GET /api/v1/security/audit`; the screenshot waits until loading ends and a real ready/empty/error row is visible. | The wide audit table scrolls inside its container, not the document. | Business-decision, Memory-mutation, and full Override history aggregate APIs are not exposed. |
| Admin overview — `admin-overview.png` | Admin inherited a generic technical landing page. | Added six legitimate product-domain entry cards without inventing IAM. | Admin receives the complete permission-derived navigation. | White overview, neutral borders, subtle selected navigation. | Unavailable aggregate summaries are labelled “汇总未开放.” | Three-column cards reflow at narrower desktop widths. | IAM, tenants, users, and role-assignment UI are deliberately deferred. |
| Vector/Shared Memory — `memory-light.png` | Existing capability remained visually dark. | Preserved tabs, query/mutation controls, provenance, and reconciliation behavior in the shared light system. | Read/mutate controls remain permission gated. | White tabs, tables, forms, evidence panels, and selected state. | API failures never fall back to demo data. | Tab content and tables use controlled internal scrolling. | No new Memory capability was added. |
| Graph Memory — `graph-light.png` | Canvas, nodes, path panel, and inspector used the old dark palette. | Migrated canvas, semantic nodes/edges, inspector, path list, selected state, and keyboard semantics. | Visibility and mutation remain permission based. | Canvas is light; inspector is computed white; selected nodes have outline plus `aria-pressed`. | Graph facts are real task evidence; absent facts show explicit state. | Canvas/inspector split scales across required viewports. | Dense central edge labels may overlap in unusually connected graphs; no large graph framework was introduced. |
| Monitoring — `monitoring-light.png` | Monitoring retained dark charts and low-contrast mixed surfaces. | Migrated live telemetry, topology, runtime cards, baseline evidence, state messages, and Grafana link. | Only roles with `monitor:read` receive this route. | Computed Monitoring panel is white; charts use light grids and teal semantic lines. | Current state is `STALE` with an explicit last-safe-sample warning; frozen acceptance values remain separately labelled `VERIFIED ACCEPTANCE BASELINE`. | Metric grid and topology remain contained at 1366/1440/1920. | Some Prometheus fixed-query groups currently return no sample, so `LIVE` is intentionally not claimed. |

## Interaction and accessibility evidence

- Canonical navigation uses links with a single active location and visible keyboard focus.
- Unauthorized routes resolve to an allowed landing or an explicit no-permission surface; backend requests still enforce 403.
- Tabs expose `aria-selected`; Graph nodes expose accessible names and `aria-pressed`.
- Runtime Intervention has an accessible dialog name, initial focus, Tab/Shift+Tab containment, Escape close, and focus restoration.
- Statuses combine text with marker/icon and semantic color.
- Tables retain captions and column headers; wide tables use container-level horizontal scrolling.
- `prefers-reduced-motion` disables non-essential transitions and skeleton shimmer.

## Evidence inventory

All browser images are under `docs/verification/frontend-role-ui/screenshots/`:

`admin-overview.png`, `auditor-audit.png`, `dispatcher-anomaly.png`, `dispatcher-dispatch.png`, `dispatcher-workspace.png`, `graph-light.png`, `memory-light.png`, `monitoring-light.png`, `operator-operations.png`, `role-preview-dev.png`, `supervisor-intervention.png`, and `supervisor-workspace.png`.

## Scope boundary

V2-F2 does not add IAM, user/tenant management, a driver application, GPS tracking, a new agent, a new database, or a new frontend framework. It preserves the existing Graph Memory, Shared Memory, Runtime Thread, Checkpoint, Runtime Override, Monitoring, and audit contracts while changing role composition and visual presentation.

## Final fresh verification

- Frontend Vitest: 38 files, 142 tests passed.
- Frontend lint: exit 0, 0 errors, 2 existing Fast Refresh export-structure warnings.
- Production build: main JS 434.82 kB / gzip 132.32 kB; CSS 65.79 kB / gzip 13.35 kB.
- Bundle delta from the pre-V2-F2 build: JS approximately +18.16 kB raw / +5.41 kB gzip; CSS approximately +23.09 kB raw / +3.60 kB gzip. No large UI, chart, or graph framework was introduced.
- Production role-switch text scan: 0 matches. Prohibited legacy dark palette scan in `frontend/src`: 0 matches.
- Backend: Ruff passed; pytest collected 703, with 696 passed and 7 Docker opt-in tests skipped in the local suite.
- V2-F2 Playwright: 1/1 full flow passed, covering all five server-issued roles, direct 403, a real Supervisor Override, computed light colors, three viewports, console/page errors, and all 12 screenshots.
- V2-G2 security: backend 100 passed, focused frontend 18 passed, real Docker controls passed, browser security 6/6 passed.
- V2-G1 observability: config/rules/targets/Grafana, failure isolation, pending/firing/resolved alert lifecycle, overhead benchmark, and browser 3/3 passed.
- Docker acceptance: 11 declared services, 10 long-running, migration exit 0, authenticated browser business regression 7/7, Backend/Frontend HTTP 200, Redis Pending 0.
- Value-based secret scan: 838 repository files scanned against 6 configured secret values, 0 findings; secret values and matching content were never printed.

### VERIFIED

Role architecture, permission navigation, role landing, non-production server-issued preview, production preview exclusion, five distinct workspaces, white enterprise theme, preserved V2 capabilities, data-truth states, responsive behavior, keyboard/accessibility contracts, security enforcement, observability behavior, and Docker topology are verified by the fresh gates above.

### DEFERRED / intentionally not exposed

Unified Review Queue, global intervention task list, Dispatcher ownership/summary projection, Anomaly and Order list/summary APIs, Auditor business-decision/Memory-mutation/full Override aggregate histories, Admin aggregate summary API, and IAM/user/tenant management remain unimplemented. Their current surfaces say `NOT EXPOSED` or “汇总未开放”; none use local arrays or fake API-mode KPI data.
