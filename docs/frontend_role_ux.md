# CountyFlow V2-F2 Role-Based Frontend UX

**Status:** IMPLEMENTED AND BROWSER VERIFIED — 2026-08-29

**Scope:** implemented information architecture, role composition, permission mapping, and UX behavior. Backend authorization remains the final security boundary.

## 1. Product model

CountyFlow remains one React/Vite SPA. It does not split into Dispatcher and Admin applications, and it does not treat hidden frontend controls as authorization.

```text
AuthenticatedPrincipal
  → normalized roles + permission set
  → RoleLandingResolver (default context only)
  → permission-filtered canonical navigation
  → shared route and workspace composition
  → route/action PermissionGate
  → backend permission enforcement
```

Roles determine the starting workspace, information order, and language. Permissions determine route visibility and actions. The backend remains the final authorization boundary for every direct request.

## 2. Role personas

### Dispatcher / 调度员

- Goal: clear today's exceptions, understand AI recommendations, start dispatches, and follow tasks to completion.
- First question: “今天哪些任务需要我处理？”
- Primary objects: anomaly, dispatch task, order, recommendation, review-needed state.
- Excludes: Monitoring, Grafana, Runtime Override, Shared Memory mutation, raw checkpoints, PromQL, Redis/Neo4j internals.

### Supervisor / 调度主管

- Goal: control business risk, review decisions, intervene at a stable runtime boundary, and verify outcomes.
- First question: “哪些 high-risk decisions or blocked tasks require a supervisor?”
- Primary objects: review queue, risk summary, intervention eligibility, override history, team task state.
- Adds to Dispatcher: `dispatch:review`, `runtime:read`, `runtime:override`, `audit:read`, `monitor:read`, and approved Memory mutation.

### Operator / 系统运维

- Goal: keep APIs, workers, streams, storage, runtime, and telemetry healthy.
- First question: “系统是否健康，哪里有 lag、pending、error or dependency degradation?”
- Primary objects: system health, QPS/P95/error, worker/stream, dependency, runtime thread summary, operational audit.
- Excludes: dispatch creation/review, order operations, Runtime Override, Memory mutation.

### Auditor / 审计员

- Goal: reconstruct who did what, why a decision was made, and whether a human or Memory mutation affected it.
- First question: “这项决策与干预的 complete evidence chain 是什么？”
- Primary objects: immutable timeline, actor, reason, decision evidence, Runtime/Override/Memory history, security events.
- All product actions are read-only. There is no create, confirm, reject, mutate, retry, or override control.

### Admin / 系统管理员

- Goal: understand product-wide business, AI, Memory, Runtime, operations, and governance health.
- First question: “系统整体是否正常，哪里需要进入专业 workspace?”
- Primary objects: product health summaries and links into existing professional surfaces.
- Excludes: invented IAM, user/organization administration, raw JSON dumps, raw checkpoints, PromQL, Redis keys, or secret-bearing configuration.

## 3. Role landing pages

| Role | Default route | Page title | First viewport | Primary action |
|---|---|---|---|---|
| Dispatcher | `/workspace` | 调度工作台 | work overview, prioritized My Tasks, dispatching now | 发起智能调度 |
| Supervisor | `/supervisor` | 调度主管台 | risk summary, Review Queue, intervention-needed tasks | 处理下一项复核 |
| Operator | `/operations` | 运行中心 | system health, QPS/P95/error, pending/lag, dependencies | 查看异常依赖 |
| Auditor | `/audit` | 审计中心 | audit event summary, intervention and mutation timeline | 打开审计证据 |
| Admin | `/overview` | 系统总览 | business, AI, Memory, Runtime, operations, governance summaries | 进入对应专业中心 |

`/` becomes a resolver, not a sixth dashboard. With the current Principal contract, multi-role default priority is `ADMIN → SUPERVISOR → OPERATOR → AUDITOR → DISPATCHER`. This priority chooses a landing page only; the union of server-issued permissions controls capabilities. A future server-owned default workspace may replace this deterministic fallback without changing page authorization.

## 4. Canonical navigation model

```ts
interface NavigationItem {
  id: string;
  label: string;
  secondaryLabel?: string;
  icon: IconType;
  route: string;
  group: "business" | "ai" | "runtime" | "operations" | "governance";
  requiredPermissions: Permission[];
  visibility: "primary" | "contextual";
}
```

The navigation registry is data, not JSX branches. An item is emitted only when the Principal has every required permission. Roles select ordering and which permitted contextual items become primary; they never grant access. Direct URL visits still pass through route-level permission gates.

### Navigation by role

| Group | Dispatcher | Supervisor | Operator | Auditor | Admin |
|---|---|---|---|---|---|
| 首页 | 调度工作台 | 调度主管台 | 运行中心 | 审计中心 | 系统总览 |
| 业务 | 异常中心、智能调度、运单管理、我的任务 | 异常中心、智能调度、运单管理、团队任务、待复核 | — | — | 异常中心、智能调度、运单管理 |
| AI | contextual AI Explanation / Evidence only | 智能体、记忆 | 智能体 | 记忆（只读） | 智能体、记忆 |
| 运行治理 | — | Runtime、Override History；Monitoring is secondary | Runtime、系统监控、Dependencies | Runtime History、Override History、Memory History、Monitoring（只读） | Runtime、Intervention、Override History、Monitoring |
| 治理 | — | 审计证据 | 必要运维审计 | 审计中心 | 审计中心；Security Summary only when exposed |

Dispatcher's `agents:read` and `memory:read` permissions support summarized evidence embedded in dispatch detail; they do not force technical top-level navigation.

## 5. Page × role matrix

Legend: `A(permission)` = visible with action; `R(permission)` = read-only; `V(permission)` = visible summary/contextual entry; `H` = hidden. Every `A/R/V` is also backend-enforced.

| Feature / page | Dispatcher | Supervisor | Operator | Auditor | Admin |
|---|---|---|---|---|---|
| 调度工作台 `/workspace` | A(`dispatch:read`) | V(`dispatch:read`) | H | H | V(`dispatch:read`) |
| 调度主管台 `/supervisor` | H | A(`dispatch:review`) | H | H | V(`dispatch:review`) |
| 运行中心 `/operations` | H | V(`monitor:read`) | A(`monitor:read`) | V(`monitor:read`) | V(`monitor:read`) |
| 审计中心 `/audit` | H | R(`audit:read`) | R(`audit:read`) | R(`audit:read`) | R(`audit:read`) |
| 系统总览 `/overview` | H | H | H | H | A(`system:admin`) |
| 异常中心 `/anomalies` | A(`anomalies:read`) | A(`anomalies:read`) | H | H | A(`anomalies:read`) |
| 智能调度 `/dispatch` | A(`dispatch:create`) | A(`dispatch:create`) | H | H | A(`dispatch:create`) |
| 调度详情 `/dispatch/:taskId` | A(`dispatch:read`) | A(`dispatch:read`) | H | H | A(`dispatch:read`) |
| 运单管理 `/orders` | A(`orders:read`) | A(`orders:read`) | H | H | A(`orders:read`) |
| 我的任务 `/my-tasks` | R(`dispatch:read`) | V(`dispatch:read`) | H | H | V(`dispatch:read`) |
| 团队任务 `/team-tasks` | H | R(`dispatch:review`) | H | H | R(`dispatch:review`) |
| 待复核 `/reviews` | H | A(`dispatch:review`) | H | H | A(`dispatch:review`) |
| 智能体中心 `/agents` | V(`agents:read`, contextual) | R(`agents:read`) | R(`agents:read`) | H | R(`agents:read`) |
| Vector Memory | V(`memory:read`, evidence) | R(`memory:read`) | H | R(`memory:read`) | R(`memory:read`) |
| Graph Memory | V(`memory:read`, summarized) | R(`memory:read`) | H | R(`memory:read`) | R(`memory:read`) |
| Shared Memory read | H | R(`memory:read`) | H | R(`memory:read`) | R(`memory:read`) |
| Shared Memory mutation | H | A(`memory:mutate`) | H | H | A(`memory:mutate`) |
| Runtime Threads `/runtime` | H | R(`runtime:read`) | R(`runtime:read`) | R(`runtime:read`) | R(`runtime:read`) |
| Review confirmation/rejection | H | A(`dispatch:review`) | H | H | A(`dispatch:review`) |
| Runtime Intervention | H | A(`runtime:override`) | H | H | A(`runtime:override`) |
| Override History | H | R(`runtime:read`) | V(`runtime:read`) | R(`runtime:read`) | R(`runtime:read`) |
| 系统监控 `/monitor` | H | R(`monitor:read`, secondary) | R(`monitor:read`) | R(`monitor:read`) | R(`monitor:read`) |
| Dependencies | H | V(`monitor:read`) | R(`monitor:read`) | V(`monitor:read`) | R(`monitor:read`) |
| Security Summary | H | H | V(`monitor:read`) | R(`audit:read`) | R(`system:admin` + exposed read contract) |

`Runtime Intervention` requires both a readable, backend-returned intervention context and `runtime:override` for the submit action. `runtime:read` alone never renders the confirm control.

## 6. Route and permission map

| Route | Required permission | Allowed actions | Role default |
|---|---|---|---|
| `/` | authenticated Principal | resolve only | none |
| `/workspace` | `dispatch:read` | read permitted modules; create CTA separately gates `dispatch:create` | Dispatcher |
| `/supervisor` | `dispatch:review` | read review/risk modules | Supervisor |
| `/operations` | `monitor:read` | read/refresh operational telemetry | Operator |
| `/audit` | `audit:read` | filter, inspect, export only if an approved export contract later exists | Auditor |
| `/overview` | `system:admin` | navigate to permitted product areas | Admin |
| `/anomalies` | `anomalies:read` | search/filter/read; dispatch link separately gates `dispatch:create` | — |
| `/dispatch` | `dispatch:create` | validate and submit async task | — |
| `/dispatch/:taskId` | `dispatch:read` | inspect progress/evidence; review and override controls use separate gates | — |
| `/orders` | `orders:read` | search/filter/read related dispatch | — |
| `/my-tasks` | `dispatch:read` | read actor-filtered tasks | — |
| `/team-tasks` | `dispatch:review` | read team task status | — |
| `/reviews` | `dispatch:review` | confirm/reject only after backend exposes review action | — |
| `/agents` | `agents:read` | inspect safe agent execution view | — |
| `/memory` | `memory:read` | inspect minimized layers; mutation separately gates `memory:mutate` | — |
| `/runtime` | `runtime:read` | inspect threads/history | — |
| `/runtime/:threadId` | `runtime:read` | inspect current state/checkpoints/history | — |
| `/runtime/:threadId/intervention` | `runtime:read` | view eligibility; submit separately gates `runtime:override` | — |
| `/monitor` | `monitor:read` | read/refresh fixed observability catalog | — |

No route is authorized by role string alone. Unauthorized direct visits render the existing explicit 403 state; expired sessions render a distinct re-authentication state.

## 7. Dispatcher flow

1. Login resolves to `/workspace`.
2. First viewport shows truthful counts for 待处理异常, 待人工确认, 调度中, 今日完成, and high-risk work. Missing read models display `NOT EXPOSED`, never zero.
3. “我的待办” orders items by risk, wait time, and business state. It does not invent ownership when actor/owner data is absent.
4. The Dispatcher opens an anomaly detail arranged as: event → AI classification → historical experience → graph evidence → weather/road → capacity → candidate routes → recommendation → allowed human action.
5. “发起智能调度” opens a real input form for anomaly description, related vehicle/route, priority, and optional context. The current fixed rain-case submission is not the target product form.
6. The async create returns a task ID and navigates immediately to execution progress.
7. The progress view translates eight agents into business steps with status, short result, and elapsed time. Raw event JSON remains hidden.
8. Completion shows recommendation, reason, evidence summary, degradation, and link to the related order/anomaly.

Dispatcher never sees Monitoring navigation or an Override action. Evidence is summarized in context even though `agents:read` and `memory:read` exist.

## 8. Supervisor flow

1. Login resolves to `/supervisor`, not the Dispatcher dashboard.
2. First viewport shows today's risk, pending review, interventions, high-risk tasks, override count, and dispatch success rate only when backed by live or verified data.
3. Review Queue shows task, AI decision, risk, reason, vehicle, route, current state, and wait time.
4. The Supervisor opens the same shared dispatch explanation surface, with a supervisor action rail added by permissions.
5. Confirm/reject uses `dispatch:review`; until a backend review endpoint exists, the queue/action is `NOT EXPOSED` and no local fake transition is allowed.
6. “进入强干预” first reads backend eligibility and stable-boundary context. The Danger Zone states entity field, old/new value, reason, expected state version, expected next agent, and downstream impact.
7. Submit requires `runtime:override`, loading and double-submit protection, explicit success/error, 409 stale-state recovery, and refreshed thread/history.
8. Override History shows time, actor, reason, old/new, state version, checkpoint, and result using the approved projection.

## 9. Operator flow

1. Login resolves to `/operations`; no dispatch CTA is present.
2. First viewport shows System Health, QPS, P95, error rate, Worker Pending, Stream Lag, and dependency health from the existing observability catalog.
3. Degraded dependencies lead to a white operations detail surface and the external Grafana link when available.
4. Runtime/agent summaries are read-only. Global Runtime Thread listing remains `NOT EXPOSED` until a bounded list projection exists.
5. Necessary audit evidence is readable; Runtime Override and Memory mutation controls do not render.

## 10. Auditor flow

1. Login resolves to `/audit`.
2. First viewport shows truthful audit categories: intervention, Memory mutation, dispatch decision, security event, failed/rejected event.
3. Filters change an immutable timeline; selecting an event opens EvidencePanel with actor, time, action, resource, reason, before/after, and approved links.
4. Runtime, Override, and Memory histories are read-only projections. Raw checkpoint payloads and secrets remain prohibited.
5. No write affordance appears. “Retry”, “confirm”, “reject”, “mutate”, “override”, and “start dispatch” are absent, not merely disabled.

## 11. Admin flow

1. Login resolves to `/overview`.
2. The overview presents six bounded summaries: business health, AI Agents, Memory, Runtime, Observability, and Governance/Security when exposed.
3. Each summary links into the shared professional page; it does not duplicate those pages.
4. Advanced Inspectors may reveal approved technical identifiers, but not raw checkpoints, Redis keys, PromQL in the product page, authorization headers, tokens, or secrets.
5. The design adds no IAM, user, organization, tenant, or Keycloak administration.

## 12. Shared composition architecture

- `RoleDashboardShell`: common responsive grid, page identity, and state boundaries.
- `WorkspaceSection`: open section with heading, actions, and loading/empty/error slots.
- `OperationalSummary`: truthful metric strip; each metric carries internal provenance metadata.
- `TaskQueue`: shared task list configured by columns and allowed actions.
- `ReviewQueue`: review-specific columns and permission-gated actions, built on `TaskQueue` primitives.
- `AgentPipeline`: existing eight-agent sequence, with business and technical presentation variants.
- `EvidencePanel`: progressive disclosure for Memory/Graph/weather/capacity/routing/audit evidence.
- `SystemHealth`: observability summary and dependency state.
- `AuditTimeline`: immutable, filterable evidence timeline.
- `PermissionGate`: route/action guard using Principal permissions.

The five landing pages are thin role compositions. Shared modules own behavior and states; role files configure module order and presentation. No five-way page fork is allowed.

## 13. Role identity and development preview

The Topbar shows display name and a localized role label, e.g. `李明 / 调度员`, with a subtle permissions/profile entry. It does not show a large Admin badge.

Development role preview is permitted only when all conditions hold:

- build environment is local, docker-dev, or test;
- authentication mode is `development_jwt`;
- the control is visibly labelled `DEV AUTH`;
- changing the preview obtains a new server-issued development session rather than constructing permissions in the browser.

Production and `oidc_jwt` builds do not include or render this control. A multi-role workspace link is not a role switch: it changes presentation only and never changes Principal claims.

Implementation truth: the development-session issuer accepts only the five allowlisted role values in local/docker-dev, derives permissions from the server-owned matrix, and returns a signed short-lived development Principal. The visible `DEV AUTH` selector obtains that session and routes through the landing resolver. Extra client fields such as `permissions` are rejected. Production compilation omits the selector and production runtime rejects the issuer.

## 14. State model

- Loading: section-level skeletons preserve table/metric layout; no whole-page “Loading...” text.
- Empty: business-specific copy and a permitted next step, such as “当前没有待处理异常”.
- Not exposed: states that the backend read contract is absent; never substitutes Demo data.
- Forbidden: stable 403 surface with route back to the user's landing page.
- Session expired: explicit re-authentication path, distinct from 403.
- API failure: bounded retry, correlation ID if safely returned, and no credential detail.
- System unavailable: operational state with safe fallback guidance; not confused with empty business data.

## 15. Data truth

UI provenance values are `LIVE`, `DEMO`, `VERIFIED`, `STALE`, and `NOT EXPOSED`. Dispatcher surfaces usually translate provenance into natural state copy; Operator, Admin, and evidence Inspectors may show the technical badge.

In API mode:

- metrics render only from live responses or clearly scoped verified evidence;
- missing endpoints render `NOT EXPOSED` rather than zero;
- errors never fall back to Mock;
- Demo role previews and data are visibly isolated from production authentication.

## 16. Accessibility and interaction

- Navigation, tabs, drawers, dialogs, tables, and row actions are keyboard reachable.
- Focus is always visible with the brand focus ring.
- Status combines text, icon/dot, and color.
- Dialogs have accessible names, initial focus, containment, Escape close, and focus restoration.
- Dense tables retain actual column headers and accessible row actions.
- Core buttons define default, hover, focus, loading, disabled, success, and error states.
- Motion is limited to 150–200ms state transitions and respects `prefers-reduced-motion`.

## 17. Responsive behavior

- 1366×768: Sidebar may start collapsed; metric strips wrap or horizontally scroll only inside the strip; primary actions and first queue remain above the fold.
- 1440×900: Sidebar defaults expanded; main content uses a balanced 12-column grid.
- 1920×1080: content max-width expands to 1680px, centered; workbench split panes grow rather than leaving all content in the upper-left.
- Tables preserve enterprise density and use controlled horizontal scrolling only when columns cannot be responsibly reduced.

## 18. Non-goals

No GPS live map, driver app, customer chat, payment, order creation platform, warehouse management, scheduling, payroll, new agent, database, IAM console, Keycloak, frontend stack migration, or production role switch is part of V2-F2.

## 19. Implemented verification state

The canonical navigation registry, Principal adapter, permission resolver, landing resolver, route guard, shared workspace primitives, and five role workspaces are implemented in `frontend/src`. Dispatcher has no Runtime Override or Monitoring entry; Supervisor can perform an eligible, versioned Runtime Intervention; Operator has no business write; Auditor is read-only and consumes the bounded Security Audit API; Admin receives all legitimate navigation without a fabricated IAM page.

Anomaly and Order API-mode static KPIs were removed. The Supervisor Review Queue, global intervention list, Auditor aggregate histories, and Admin aggregate summaries remain explicit `NOT EXPOSED` gaps. Required 1366, 1440, and 1920 browser viewports, computed light surfaces, five server-issued roles, direct 403 enforcement, production switch exclusion, and real Runtime Override were exercised by Playwright. The page-by-page ledger and screenshots are in `docs/verification/frontend-role-ui/`.
