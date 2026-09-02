# Driver Anomaly Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow an authenticated delivery employee to report a structured problem from an assigned non-ended task, automatically create an idempotent Anomaly and DispatchTask, launch the existing Redis Streams/8-Agent flow, and replace the dispatcher’s hard-coded submission page with a task center.

**Architecture:** Add a narrow `AnomalyReportService` in front of the existing `DispatchTaskApiService`. The report service validates ownership, derives order/driver/vehicle/route server-side, persists report provenance, then delegates task idempotency and Stream publication to the existing service. The React employee flow adds `/report-issue`, while `/dispatch` becomes a read-only anomaly/task center.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic, Redis Streams, pytest, React 19, TypeScript, React Router, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-01-driver-anomaly-reporting-design.md`

## Global Constraints

- Use TDD: write a behavior-level failing test, run it, implement the smallest real behavior, rerun it.
- API handlers depend on application services and must not import Redis, SQLAlchemy repositories, Qdrant, Neo4j, or vendor SDKs directly.
- Reuse the existing `DispatchTaskApiService`, Redis Stream, Runtime Thread, Worker and 8-Agent LangGraph.
- EMPLOYEE gains only `anomalies:report`; it must not gain `dispatch:create`.
- Derive order, driver, vehicle, route and assignee from the authenticated employee’s source task.
- Reuse `MY_TASK_STATUS_GROUPS`: READY, WAITING and ACTIVE are reportable; ENDED is not.
- Reuse the `DISPATCH_SUBMIT` rate-limit operation class.
- API mode must never fall back to mock success.
- Do not add photos, GPS, file storage, new Agents, new infrastructure or new external providers.
- Preserve existing staged and untracked user changes. Do not commit while the repository has no safe baseline and unrelated staged content.
- After each task inspect the scoped diff; before completion run the full required verification.

---

## File Structure

### Backend create

- `backend/app/anomaly_reports/__init__.py`: public package exports.
- `backend/app/anomaly_reports/models.py`: report command/result and repository records.
- `backend/app/anomaly_reports/protocols.py`: narrow repository Protocol.
- `backend/app/anomaly_reports/service.py`: ownership, idempotency and dispatch orchestration.
- `backend/app/anomaly_reports/sqlalchemy_repository.py`: Order/Task/Anomaly persistence adapter.
- `backend/app/api/v1/anomaly_report_schemas.py`: request/response schema.
- `backend/app/api/v1/anomaly_reports.py`: permission/rate-limit/error mapping router.
- `backend/alembic/versions/20260901_11_driver_anomaly_reports.py`: provenance/idempotency columns and indexes.
- `backend/tests/anomaly_reports/test_anomaly_report_service.py`: service behavior tests.
- `backend/tests/api/test_anomaly_reports.py`: endpoint and permission tests.
- `backend/tests/migrations/test_driver_anomaly_report_migration.py`: migration contract.

### Backend modify

- `backend/app/models/anomaly.py`: report provenance fields.
- `backend/app/security/permissions.py`: `ANOMALIES_REPORT` permission and matrix.
- `backend/app/security/audit.py`: stable report audit event types/reason codes where required.
- `backend/app/main.py`: application service construction and router inclusion.
- `backend/tests/security/test_permissions.py`: exact matrix expectations.
- `backend/tests/api/test_endpoint_permissions.py`: report endpoint role matrix.

### Frontend create

- `frontend/src/types/anomaly-report.ts`: report enums and API contracts.
- `frontend/src/services/api/anomaly-report-client.ts`: POST client.
- `frontend/src/features/anomaly-report/submission.ts`: stable idempotency and form validation.
- `frontend/src/pages/report-issue-page.tsx`: employee report page.
- `frontend/tests/report-issue-page.test.tsx`: form behavior.
- `frontend/src/pages/dispatch-task-center-page.tsx`: read-only dispatcher task center.
- `frontend/tests/dispatch-task-center-page.test.tsx`: no hard-coded submission behavior.
- `frontend/e2e/driver-anomaly-report.spec.ts`: role and workflow browser coverage.

### Frontend modify

- `frontend/src/auth/permissions.ts`: `ANOMALIES_REPORT` and role matrix.
- `frontend/src/app/router.tsx`: `/report-issue` and new dispatch center component.
- `frontend/src/navigation/navigation-registry.ts`: employee report entry.
- `frontend/src/components/app-shell.tsx`: route label.
- `frontend/src/pages/my-tasks-page.tsx`: header/row report actions.
- `frontend/src/styles/index.css`: report form/task-center styles.
- Existing tests covering navigation, role landing, My Tasks and light UI.

---

### Task 1: Permission Contract and Anomaly Schema

**Files:**
- Modify: `backend/app/security/permissions.py`
- Modify: `backend/app/models/anomaly.py`
- Create: `backend/alembic/versions/20260901_11_driver_anomaly_reports.py`
- Modify: `backend/tests/security/test_permissions.py`
- Create: `backend/tests/migrations/test_driver_anomaly_report_migration.py`

**Interfaces:**
- Produces: `Permission.ANOMALIES_REPORT = "anomalies:report"`.
- Produces: `Anomaly.reported_by_subject_id`, `source_task_id`, `location_text`, `reported_vehicle_status`, `report_idempotency_key`.
- Consumes: current Role/Permission matrix and Alembic revision `20260830_10`.

- [ ] **Step 1: Write the failing permission test**

```python
def test_employee_can_report_anomaly_without_dispatch_create() -> None:
    assert Permission.ANOMALIES_REPORT in ROLE_PERMISSION_MATRIX[Role.EMPLOYEE]
    assert Permission.DISPATCH_CREATE not in ROLE_PERMISSION_MATRIX[Role.EMPLOYEE]
    assert Permission.ANOMALIES_REPORT not in ROLE_PERMISSION_MATRIX[Role.DISPATCHER]
    assert ROLE_PERMISSION_MATRIX[Role.ADMIN] == ALL_PERMISSIONS
```

- [ ] **Step 2: Run the permission test and confirm failure**

Run: `pytest backend/tests/security/test_permissions.py -q`

Expected: FAIL because `Permission.ANOMALIES_REPORT` does not exist.

- [ ] **Step 3: Implement the minimal permission change**

Add:

```python
class Permission(StrEnum):
    ANOMALIES_REPORT = "anomalies:report"
```

Change only the EMPLOYEE permission set; ADMIN receives it through `ALL_PERMISSIONS`.

- [ ] **Step 4: Write the failing model/migration test**

Assert that the model exposes all five fields, `report_idempotency_key` is unique, and the migration revision/down_revision are:

```python
revision = "20260901_11"
down_revision = "20260830_10"
```

- [ ] **Step 5: Run the migration test and confirm failure**

Run: `pytest backend/tests/migrations/test_driver_anomaly_report_migration.py -q`

Expected: FAIL because the revision and fields do not exist.

- [ ] **Step 6: Implement the model and migration**

Use nullable columns for legacy rows:

```python
reported_by_subject_id: Mapped[str | None] = mapped_column(String(128), index=True)
source_task_id: Mapped[str | None] = mapped_column(String(36), index=True)
location_text: Mapped[str | None] = mapped_column(String(255))
reported_vehicle_status: Mapped[str | None] = mapped_column(String(32))
report_idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
```

The migration must create named indexes and a named unique constraint, and downgrade them in reverse order.

- [ ] **Step 7: Run Task 1 tests**

Run: `pytest backend/tests/security/test_permissions.py backend/tests/migrations/test_driver_anomaly_report_migration.py -q`

Expected: PASS.

- [ ] **Step 8: Inspect the scoped diff**

Run: `git diff -- backend/app/security/permissions.py backend/app/models/anomaly.py backend/alembic/versions/20260901_11_driver_anomaly_reports.py backend/tests/security/test_permissions.py backend/tests/migrations/test_driver_anomaly_report_migration.py`

---

### Task 2: Anomaly Report Repository and Service

**Files:**
- Create: `backend/app/anomaly_reports/__init__.py`
- Create: `backend/app/anomaly_reports/models.py`
- Create: `backend/app/anomaly_reports/protocols.py`
- Create: `backend/app/anomaly_reports/sqlalchemy_repository.py`
- Create: `backend/app/anomaly_reports/service.py`
- Create: `backend/tests/anomaly_reports/test_anomaly_report_service.py`

**Interfaces:**
- Consumes: `DispatchTaskApiService.submit(request, assignee_subject_id=...)`.
- Produces: `AnomalyReportCommand`, `AnomalyReportResult`, `AnomalyReportService.submit(command, principal_subject_id)`.
- Produces errors: `SourceTaskNotFound`, `ReportSourceForbidden`, `SourceTaskEnded`, `SourceContextIncomplete`, `ReportIdempotencyConflict`, `ReportQueueUnavailable`.

- [ ] **Step 1: Write failing service tests for ownership and derivation**

Seed two EMPLOYEE accounts, two orders and source tasks. Assert:

```python
result = await service.submit(command(source_task_id="TASK-OWNED"), principal_subject_id="CF-DEMO-001")
assert result.anomaly.order_id == owned_order.id
assert captured_dispatch.driver_id == owned_order.driver_id
assert captured_dispatch.vehicle_id == owned_order.vehicle_id
assert captured_dispatch.route_id == owned_order.route_id
assert captured_assignee == "CF-DEMO-001"
```

Also assert another employee receives `ReportSourceForbidden` and an ENDED task receives `SourceTaskEnded`.

- [ ] **Step 2: Run service tests and confirm failure**

Run: `pytest backend/tests/anomaly_reports/test_anomaly_report_service.py -q`

Expected: collection/import failure because the package is absent.

- [ ] **Step 3: Define focused application models and Protocol**

```python
@dataclass(frozen=True)
class AnomalyReportCommand:
    source_task_id: str
    anomaly_type: str
    description: str
    location_text: str
    reported_vehicle_status: str
    severity: str
    idempotency_key: str

@dataclass(frozen=True)
class AnomalyReportResult:
    anomaly_id: int
    anomaly_no: str
    task_id: str
    status: str
    duplicate: bool
```

The repository Protocol must expose narrow methods for source context lookup, report-by-key lookup and report creation. It must not expose a SQLAlchemy Session.

- [ ] **Step 4: Implement SQLAlchemy adapter and minimal service**

Rules:

```python
REPORTABLE_GROUPS = frozenset({"READY", "WAITING", "ACTIVE"})
```

Map raw statuses using the existing `MY_TASK_STATUS_GROUPS`. Generate `anomaly_no` server-side. Build `CreateDispatchTaskRequest` only from persisted source context and report content. Derive the task idempotency key as `f"anomaly-report:{sha256(command.idempotency_key.encode()).hexdigest()}"`, keeping it within the existing 128-character column.

- [ ] **Step 5: Add failing idempotency and queue recovery tests**

Assert same report key returns the same anomaly/task; changed content raises conflict; `SubmissionQueueError` becomes `ReportQueueUnavailable` containing recoverable identities; retry calls the existing task service with the same derived key.

- [ ] **Step 6: Implement idempotent replay and queue error translation**

Store a normalized content fingerprint with the report application record or compare persisted report fields plus source task. On `SubmissionQueueError`, look up the existing DispatchTask by derived key and raise a typed error containing anomaly/task identity without exposing internal exception text.

- [ ] **Step 7: Run Task 2 tests**

Run: `pytest backend/tests/anomaly_reports/test_anomaly_report_service.py -q`

Expected: PASS.

- [ ] **Step 8: Inspect scoped diff**

Run: `git diff -- backend/app/anomaly_reports backend/tests/anomaly_reports`

---

### Task 3: FastAPI Contract, Wiring and Security Audit

**Files:**
- Create: `backend/app/api/v1/anomaly_report_schemas.py`
- Create: `backend/app/api/v1/anomaly_reports.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/security/audit.py`
- Create: `backend/tests/api/test_anomaly_reports.py`
- Modify: `backend/tests/api/test_endpoint_permissions.py`

**Interfaces:**
- Consumes: `AnomalyReportService.submit` and Task 2 typed errors.
- Produces: `POST /api/v1/anomaly-reports` returning `AnomalyReportResponse`.

- [ ] **Step 1: Write failing API success and ownership tests**

Create an injected fake service and assert:

```python
response = client.post("/api/v1/anomaly-reports", headers=employee_headers, json=payload)
assert response.status_code == 202
assert response.json()["task_id"] == "TASK-NEW"
assert fake_service.subject_id == employee_principal.subject_id
```

Assert DISPATCHER receives 403 and the request schema does not accept order/driver/vehicle/route/assignee fields (`extra="forbid"`).

- [ ] **Step 2: Run API tests and confirm failure**

Run: `pytest backend/tests/api/test_anomaly_reports.py -q`

Expected: FAIL because the router is absent.

- [ ] **Step 3: Implement request/response schemas**

Use `ConfigDict(extra="forbid")`, description length 5–2000, location length 1–255 and Literal/Enum validation for anomaly type, vehicle status and severity.

- [ ] **Step 4: Implement router and stable error mapping**

Map typed errors exactly:

```text
403 REPORT_SOURCE_FORBIDDEN
404 SOURCE_TASK_NOT_FOUND
409 SOURCE_TASK_ENDED
409 IDEMPOTENCY_CONFLICT
422 SOURCE_CONTEXT_INCOMPLETE
503 REPORT_QUEUE_UNAVAILABLE
```

Use `require_permission(Permission.ANOMALIES_REPORT)` and `require_rate_limit(OperationClass.DISPATCH_SUBMIT)`.

- [ ] **Step 5: Wire service into `create_app`**

Add optional `anomaly_report_service` injection for tests. Construct the production service from the session factory and existing `app.state.dispatch_task_api_service`, assign it to app state, and include the router after the dispatch task service exists.

- [ ] **Step 6: Add audit assertions**

Record stable allowed/denied reason codes without full descriptions or credentials. Update exact endpoint permission matrix tests.

- [ ] **Step 7: Run Task 3 tests**

Run: `pytest backend/tests/api/test_anomaly_reports.py backend/tests/api/test_endpoint_permissions.py backend/tests/security/test_permissions.py -q`

Expected: PASS.

- [ ] **Step 8: Inspect scoped diff**

Run: `git diff -- backend/app/api/v1/anomaly_report_schemas.py backend/app/api/v1/anomaly_reports.py backend/app/main.py backend/app/security/audit.py backend/tests/api/test_anomaly_reports.py backend/tests/api/test_endpoint_permissions.py`

---

### Task 4: Frontend API Client and Submission State

**Files:**
- Create: `frontend/src/types/anomaly-report.ts`
- Create: `frontend/src/services/api/anomaly-report-client.ts`
- Create: `frontend/src/features/anomaly-report/submission.ts`
- Create: `frontend/tests/anomaly-report-submission.test.ts`
- Modify: `frontend/src/auth/permissions.ts`

**Interfaces:**
- Produces: `AnomalyReportRequest`, `AnomalyReportResponse`, `AnomalyReportClient.report`.
- Produces: `createAnomalyReportSubmission(reportTask, createKey)` that retains one idempotency key across retries.

- [ ] **Step 1: Write failing TypeScript submission tests**

```typescript
it("reuses one idempotency key when a saved report retries queue publication", async () => {
  const calls: AnomalyReportRequest[] = [];
  const submission = createAnomalyReportSubmission(async (request) => {
    calls.push(request);
    if (calls.length === 1) throw new ApiError(503, "REPORT_QUEUE_UNAVAILABLE", "retry");
    return acceptedReport;
  }, () => "report-key-1");
  await expect(submission.submit(form)).rejects.toMatchObject({ code: "REPORT_QUEUE_UNAVAILABLE" });
  await submission.submit(form);
  expect(calls.map((item) => item.idempotency_key)).toEqual(["report-key-1", "report-key-1"]);
});
```

- [ ] **Step 2: Run the test and confirm failure**

Run: `npm test -- --run tests/anomaly-report-submission.test.ts` from `frontend/`.

Expected: FAIL because the module is absent.

- [ ] **Step 3: Implement types, client and submission controller**

POST to `/api/v1/anomaly-reports`. Keep API codes in English enums and presentation labels elsewhere. Add `ANOMALIES_REPORT` to the frontend permission matrix for EMPLOYEE and ADMIN only.

- [ ] **Step 4: Run Task 4 tests**

Run: `npm test -- --run tests/anomaly-report-submission.test.ts` from `frontend/`.

Expected: PASS.

- [ ] **Step 5: Inspect scoped diff**

Run: `git diff -- frontend/src/types/anomaly-report.ts frontend/src/services/api/anomaly-report-client.ts frontend/src/features/anomaly-report frontend/src/auth/permissions.ts`

---

### Task 5: Driver Report Page and My Tasks Entry

**Files:**
- Create: `frontend/src/pages/report-issue-page.tsx`
- Create: `frontend/tests/report-issue-page.test.tsx`
- Modify: `frontend/src/pages/my-tasks-page.tsx`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/navigation/navigation-registry.ts`
- Modify: `frontend/src/components/app-shell.tsx`
- Modify: `frontend/src/styles/index.css`
- Modify: related My Tasks/navigation tests.

**Interfaces:**
- Consumes: Task 4 submission controller and existing `useMyTasksRead`.
- Produces: permission-gated `/report-issue?taskId=` page.

- [ ] **Step 1: Write failing page tests**

Cover:

```typescript
expect(screen.getByRole("heading", { name: "提出配送问题" })).toBeInTheDocument();
expect(screen.getByLabelText("当前任务")).toHaveValue("TASK-OWNED");
expect(screen.getByRole("button", { name: "提交问题并启动 AI 调度" })).toBeEnabled();
```

Also assert required validation, 503 saved/retry copy, success identities and no mock fallback.

- [ ] **Step 2: Run page tests and confirm failure**

Run: `npm test -- --run tests/report-issue-page.test.tsx` from `frontend/`.

Expected: FAIL because the page is absent.

- [ ] **Step 3: Implement the page**

Render a read-only task-context card, structured form and submission explanation. Use native labels, accessible error summary and status-specific feedback. On success link to `/dispatch/${task_id}` and `/my-tasks`.

- [ ] **Step 4: Add My Tasks entry tests**

Assert READY/WAITING/ACTIVE rows show “报告问题”, ENDED rows do not, and EMPLOYEE sees the page-level entry. Do not infer ownership client-side beyond server-owned My Tasks data.

- [ ] **Step 5: Implement My Tasks, router and navigation changes**

Route `/report-issue` through `RequirePermission permission="anomalies:report"`. Preserve EMPLOYEE landing at `/my-tasks`.

- [ ] **Step 6: Run Task 5 tests**

Run: `npm test -- --run tests/report-issue-page.test.tsx tests/my-tasks-page.test.tsx` from `frontend/`.

Expected: PASS.

- [ ] **Step 7: Inspect scoped diff**

Run: `git diff -- frontend/src/pages/report-issue-page.tsx frontend/src/pages/my-tasks-page.tsx frontend/src/app/router.tsx frontend/src/navigation/navigation-registry.ts frontend/src/components/app-shell.tsx frontend/src/styles/index.css`

---

### Task 6: Replace Hard-Coded Dispatch Start with Task Center

**Files:**
- Create: `frontend/src/pages/dispatch-task-center-page.tsx`
- Create: `frontend/tests/dispatch-task-center-page.test.tsx`
- Modify: `frontend/src/app/router.tsx`
- Remove API-mode use of: `frontend/src/components/dispatch-submission-button.tsx`
- Remove API-mode use of: `frontend/src/features/dispatch/submission.ts` `coreRainDispatch`
- Update E2E expectations in `frontend/e2e/role-based-light-ui.spec.ts`.

**Interfaces:**
- Consumes: existing `useAnomaliesRead` and `AnomalyListItem.latest_task_id`.
- Produces: read-only `/dispatch` task center.

- [ ] **Step 1: Write failing task-center test**

Assert the page heading is “异常调度任务”, recent anomalies render with task links, and no “发起 AI 调度” button or fixed “李师傅 · 新平路” copy exists.

- [ ] **Step 2: Run the test and confirm failure**

Run: `npm test -- --run tests/dispatch-task-center-page.test.tsx` from `frontend/`.

Expected: FAIL because the page is absent/current route still uses DispatchStartPage.

- [ ] **Step 3: Implement minimal task center**

Use existing anomaly read states: LOADING, EMPTY, FORBIDDEN, UNAVAILABLE and READY. Link `latest_task_id` to `/dispatch/:taskId`; show “等待自动任务” when absent. Provide a Reviews link for permitted roles.

- [ ] **Step 4: Remove stale page behavior**

Switch `/dispatch` to `DispatchTaskCenterPage`. Remove or isolate the fixed submission component so API mode has no callable fixed case. Correct “七智能体” to “8-Agent” wherever still user-visible.

- [ ] **Step 5: Run Task 6 tests**

Run: `npm test -- --run tests/dispatch-task-center-page.test.tsx` from `frontend/`.

Expected: PASS.

- [ ] **Step 6: Inspect scoped diff**

Run: `git diff -- frontend/src/pages/dispatch-task-center-page.tsx frontend/src/app/router.tsx frontend/src/components/dispatch-submission-button.tsx frontend/src/features/dispatch/submission.ts frontend/e2e/role-based-light-ui.spec.ts`

---

### Task 7: Integrated Verification and Documentation Alignment

**Files:**
- Create/Modify: `frontend/e2e/driver-anomaly-report.spec.ts`
- Modify only if facts changed: `docs/final/FINAL_FACTS.md` and affected final reports.
- Review all files changed by Tasks 1–6.

**Interfaces:**
- Consumes: complete backend API and frontend flow.
- Produces: verified driver report flow with explicit environment limitations.

- [ ] **Step 1: Add browser workflow test**

Cover EMPLOYEE login → My Tasks → report issue → receive task id → view progress. Add a cross-employee forbidden API assertion and 390×844 no-horizontal-overflow assertion.

- [ ] **Step 2: Run targeted backend tests**

Run:

```text
ruff check backend
pytest backend/tests/anomaly_reports backend/tests/api/test_anomaly_reports.py backend/tests/security/test_permissions.py backend/tests/migrations/test_driver_anomaly_report_migration.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full backend tests**

Run the repository’s approved isolated test command if the ignored `.env` still contains an invalid development JWT secret; record both the default gate and isolated result without printing the secret.

Expected: no regressions relative to the current 833 passed / 7 skipped baseline, adjusted upward for new tests.

- [ ] **Step 4: Run frontend gates**

From `frontend/` run:

```text
npm test
npm run lint
npm run build
```

Expected: all tests pass, ESLint has no errors, Vite build succeeds.

- [ ] **Step 5: Run Playwright when the live stack is available**

Run: `npx playwright test driver-anomaly-report.spec.ts` from `frontend/`.

If Docker/browser dependencies are unavailable, mark this NOT RE-VERIFIED; do not claim PASS.

- [ ] **Step 6: Inspect all diffs and placeholders**

Run:

```text
rg -n -i "\b(TBD|TODO|PLACEHOLDER|UNKNOWN)\b" backend/app/anomaly_reports backend/app/api/v1/anomaly_reports.py frontend/src/pages/report-issue-page.tsx docs/superpowers
git -c safe.directory=<workspace> diff --check
git -c safe.directory=<workspace> diff --cached --check
git -c safe.directory=<workspace> status --short --branch
```

Expected: no new placeholders or whitespace errors. Existing unrelated staged/untracked files remain untouched.

- [ ] **Step 7: Update factual docs only when implementation evidence exists**

Update role permission, endpoint, page and test counts from actual outputs. Do not mark browser/Docker evidence VERIFIED unless the commands ran successfully in this implementation turn.

---

## Completion Checklist

- [x] EMPLOYEE can report from READY/WAITING/ACTIVE assigned tasks.
- [x] ENDED and foreign tasks are rejected server-side.
- [x] Server derives all dispatch context.
- [x] One report creates one Anomaly and one DispatchTask.
- [x] Queue failure is retryable with the same identities.
- [x] Existing 8-Agent flow executes unchanged.
- [x] Driver sees progress and only published route details.
- [x] Dispatcher `/dispatch` contains no hard-coded submission.
- [x] Backend targeted and full tests are recorded.
- [x] Frontend unit, lint and build are recorded.
- [x] Browser result is recorded honestly.
- [x] Git diff checks are clean.
