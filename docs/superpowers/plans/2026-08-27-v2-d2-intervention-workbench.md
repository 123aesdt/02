# V2-D2 Runtime Intervention Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` for every behavior change and `superpowers:verification-before-completion` before reporting completion. Execute this plan task-by-task with review checkpoints.

**Goal:** Add a safe, auditable Runtime Intervention Workbench to the existing dispatch detail page and prove it through real API-mode Playwright tests against the nine-service Docker runtime.

**Architecture:** Keep the V2-D1 write core frozen. Add a read-side intervention query service for authoritative eligibility and bounded history, complete safe task-event DTOs, and build a React workbench whose dialog freezes canonical preconditions and uses HTTP as truth plus WebSocket-triggered refetch. Mock and API paths remain explicitly separate.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, MySQL 8.4, Redis 8.2.9, LangGraph AsyncRedisSaver, React, TypeScript, Vitest, Playwright 1.62.1, Docker Compose, PowerShell.

**Spec:** `docs/superpowers/specs/2026-08-27-v2-d2-intervention-workbench-design.md`

## Global constraints

- Do not modify the V2-D1 lock order, policy allowlist, official `aupdate_state` flow, checkpoint validator, canonical promotion, idempotency, or reconciler semantics.
- The only writable target is `Vehicle.status`, from `NORMAL` to `BROKEN`, `UNAVAILABLE`, or `MAINTENANCE`, at `environment -> capacity`.
- HTTP/GET is business truth; WebSocket is notification and a refetch trigger.
- API mode never falls back to mock data.
- Formal browser acceptance uses real Docker Redis, MySQL, AsyncRedisSaver, backend, workers, and runtime override; no fakeredis or SQLite.
- Do not add application Pause, Resume, rollback, goto, skip, rerun, arbitrary state paths, or arbitrary JSON controls.
- Preserve the ordinary `memory-rain-li -> national-102 -> REROUTE -> APPROVED` flow and Redis Pending `0`.
- Preserve user-owned workspace changes. Inspect diffs after every task and do not create commits unless the user explicitly requests them.

---

## Task 1: Authoritative intervention eligibility read model

**Files:**

- Create: `backend/app/runtime_overrides/query_models.py`
- Create: `backend/app/runtime_overrides/query_service.py`
- Modify: `backend/app/runtime_overrides/__init__.py`
- Test: `backend/tests/runtime_overrides/test_query_service.py`

**Interfaces:**

- Consumes: `RuntimeThreadRepository.get_by_thread_id`, `RuntimeCheckpointStore.get_exact`, and `RuntimeThreadAuthorizer.authorize_read/authorize_override`.
- Produces: `RuntimeInterventionEligibility`, `RuntimeInterventionTarget`, `RuntimeInterventionContext`, and `RuntimeOverrideQueryService.get_intervention_context(thread_id)`.

- [ ] **Step 1: Write RED tests for all eligibility states**

Create table-driven tests named:

```python
async def test_intervention_context_eligible(): ...
async def test_intervention_context_not_stable(): ...
async def test_intervention_context_terminal(): ...
async def test_intervention_context_no_permission(): ...
async def test_intervention_context_wrong_boundary(): ...
async def test_intervention_context_busy(): ...
async def test_intervention_context_uses_exact_canonical_checkpoint(): ...
```

The eligible fixture must be `STABLE`, current node `environment`, next node `capacity`, exact canonical state `{"vehicle_id": "vehicle-001", "vehicle_status": "NORMAL"}`, and permissions containing `runtime:read` and `runtime:override`. Assert allowed values are exactly `BROKEN`, `UNAVAILABLE`, and `MAINTENANCE`.

- [ ] **Step 2: Run RED and confirm missing query types/service**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/runtime_overrides/test_query_service.py -q
```

Expected: collection/import failure because `query_models` and `query_service` do not exist.

- [ ] **Step 3: Implement immutable read models and precedence**

Define:

```python
class RuntimeInterventionEligibility(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    NOT_STABLE = "NOT_STABLE"
    TERMINAL = "TERMINAL"
    NO_PERMISSION = "NO_PERMISSION"
    WRONG_BOUNDARY = "WRONG_BOUNDARY"
    BUSY = "BUSY"

@dataclass(frozen=True)
class RuntimeInterventionTarget:
    entity_type: str
    entity_id: str
    display_name: str
    field: str
    current_value: str
    allowed_new_values: tuple[str, ...]

@dataclass(frozen=True)
class RuntimeInterventionContext:
    thread_id: str
    task_id: str
    runtime_status: str
    state_version: int
    current_node: str | None
    next_node: str | None
    canonical_checkpoint_id: str | None
    checkpoint_available: bool
    eligibility: RuntimeInterventionEligibility
    eligibility_reason_code: str | None
    can_override: bool
    target: RuntimeInterventionTarget | None
    observed_at: datetime
```

Implement precedence `NO_PERMISSION`, `TERMINAL`, `BUSY`, `NOT_STABLE`, `WRONG_BOUNDARY`, `ELIGIBLE`. Use only the exact checkpoint addressed by the MySQL canonical pointer. Missing/unavailable checkpoint returns a safe query-service error mapped later to 503; it never selects Redis latest.

- [ ] **Step 4: Run GREEN**

Run the Task 1 test file and confirm every case passes.

- [ ] **Step 5: REFACTOR and inspect scope**

Keep eligibility mapping pure and separate from I/O. Re-run Task 1 tests and inspect:

```powershell
git diff -- backend/app/runtime_overrides/query_models.py backend/app/runtime_overrides/query_service.py backend/tests/runtime_overrides/test_query_service.py
```

---

## Task 2: Authenticated intervention and bounded history APIs

**Files:**

- Modify: `backend/app/runtime_overrides/sqlalchemy_repository.py`
- Modify: `backend/app/api/v1/runtime_override_schemas.py`
- Modify: `backend/app/api/v1/runtime_overrides.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/runtime_overrides/test_repository.py`
- Test: `backend/tests/api/test_runtime_overrides.py`

**Interfaces:**

- Consumes: Task 1 `RuntimeOverrideQueryService` and existing `StoredRuntimeOverride`.
- Produces:
  - `GET /api/v1/runtime/threads/{thread_id}/intervention`
  - `GET /api/v1/runtime/threads/{thread_id}/overrides?limit=20`
  - authenticated `GET /api/v1/runtime/overrides/{override_id}`
  - `RuntimeInterventionContextResponse` and `RuntimeOverrideHistoryResponse`.

- [ ] **Step 1: Write repository RED tests**

Add tests proving `list_by_thread(thread_id, limit)` is newest-first, never returns another thread, and enforces `1 <= limit <= 100` at the service/API boundary.

- [ ] **Step 2: Write API RED tests**

Add tests for eligible context, `NO_PERMISSION`, forbidden read, bounded history, safe fields, missing thread, and checkpoint-store unavailable. Add exact POST response tests: terminal maps to HTTP 409, version/busy/not-stable conflicts map to 409, field/value rejection maps to 422, forbidden maps to 403, and checkpoint-store failure maps to 503. Assert history JSON contains no `idempotency_key`, `payload_fingerprint`, `operator_permissions`, `state`, or checkpoint payload.

- [ ] **Step 3: Run RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/runtime_overrides/test_repository.py backend/tests/api/test_runtime_overrides.py -q
```

Expected: failures for absent list method, response schemas, query dependency, and routes.

- [ ] **Step 4: Implement the smallest read API**

Add `SqlAlchemyRuntimeOverrideRepository.list_by_thread(thread_id, limit)`. Add response models aligned with the design. Split router dependencies into command service for POST and query service for GET. Replace generic status-only POST mapping with a small explicit safe error-code-to-HTTP map that preserves response bodies and does not affect service execution. Wire one query service in `create_app` using the same session factory, exact checkpoint store, runtime-thread repository, and authorizer already constructed for D1.

Do not expose the idempotency key or fingerprint in history. Keep POST routed to the existing `RuntimeOverrideService.apply` unchanged.

- [ ] **Step 5: Run GREEN and regression**

Run the Task 2 tests, then:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/runtime_overrides backend/tests/api/test_runtime_overrides.py backend/tests/api/test_runtime_threads.py -q
```

- [ ] **Step 6: REFACTOR**

Remove duplicate schema conversion with one safe mapper. Keep query authorization in the query service rather than the React-facing router. Inspect only Task 2 files.

---

## Task 3: Complete safe override and Capacity event DTOs

**Files:**

- Modify: `backend/app/runtime_overrides/events.py`
- Modify: `backend/app/runtime_overrides/service.py`
- Modify: `backend/app/events/graph_adapter.py`
- Test: `backend/tests/runtime_overrides/test_events.py`
- Test: `backend/tests/graph/test_capacity_agent.py`
- Test: `backend/tests/api/test_task_events.py`

**Interfaces:**

- Consumes: existing `RuntimeOverrideEventPublisher`, `TaskEvent`, graph updates, and canonical accumulated state.
- Produces: complete requested/applied/rejected/conflict/partial notifications and a safe `CAPACITY_COMPLETED` payload.

- [ ] **Step 1: Write RED event tests**

Assert override events include bounded actor, role, reason, expected version/next node, safe transition, status/error code, and applicable checkpoint/version fields. Assert they exclude idempotency key, fingerprints, tokens, full state, and raw exceptions.

Add a service-level test proving a returned `CONFLICT`, `REJECTED`, or `PARTIAL` publishes the matching event once. Preserve the existing rule that event delivery failure cannot turn canonical `APPLIED` into a failed state mutation.

- [ ] **Step 2: Write RED Capacity event test**

Run a Capacity update with canonical `vehicle_id=vehicle-001` and `vehicle_status=BROKEN`. Assert `CAPACITY_COMPLETED.data` includes:

```python
{
    "vehicle_id": "vehicle-001",
    "vehicle_status": "BROKEN",
    "driver_available": True,
    "vehicle_available": False,
    "capacity_status": "UNAVAILABLE",
    "risk_level": "high",
    "reason": "Vehicle runtime status is BROKEN.",
}
```

- [ ] **Step 3: Run RED**

Run the three Task 3 test files and confirm payload/status-event assertions fail against the current implementation.

- [ ] **Step 4: Implement event completion without changing D1 ordering**

Extend the event publisher safe payload. Route non-APPLIED stored results through its existing `publish_status` behavior exactly once. Refactor `GraphEventAdapter.publish_completed` to receive accumulated safe graph state for event projection; do not change the Capacity node state patch. Project only the allowlisted Capacity fields.

- [ ] **Step 5: Run GREEN and D1 regression**

Run Task 3 tests plus all runtime-override service/reconciler tests. Confirm lock/CAS/promotion assertions are unchanged.

---

## Task 4: Frontend types and HTTP client

**Files:**

- Create: `frontend/src/types/runtime-override.ts`
- Create: `frontend/src/services/api/runtime-override-client.ts`
- Modify: `frontend/src/services/api/client.ts`
- Test: `frontend/tests/runtime-override-client.test.ts`
- Test: `frontend/tests/api-client-errors.test.ts`

**Interfaces:**

- Consumes: Task 2 JSON schemas.
- Produces: `RuntimeOverrideClient`, `HttpRuntimeOverrideClient`, and exact snake_case TypeScript contracts.

- [ ] **Step 1: Write RED client tests**

Test each endpoint path, URL encoding, bounded history limit, JSON POST body, AbortSignal forwarding, HTTP 202 `PARTIAL` handling, and structured error preservation.

For 422, assert a body `{ "code": "OVERRIDE_VALUE_INVALID", "message": "..." }` produces `ApiError.code === "OVERRIDE_VALUE_INVALID"`; FastAPI field-error arrays still map to `VALIDATION_ERROR`.

- [ ] **Step 2: Run RED**

Run:

```powershell
Set-Location frontend
npm test -- runtime-override-client.test.ts api-client-errors.test.ts
```

Expected: missing module failures and the current generic 422 mapping failure.

- [ ] **Step 3: Implement exact contracts and client**

Define `RuntimeOverrideStatus`, eligibility, target/context, request/response/detail/history, and submission-state unions. Implement the four methods from the design. Do not translate backend field names into a second vocabulary.

- [ ] **Step 4: Run GREEN and REFACTOR**

Run Task 4 tests. Share the existing `createApiClient`; do not add direct `fetch` calls or duplicate base URL logic.

---

## Task 5: Runtime workbench data orchestration

**Files:**

- Create: `frontend/src/hooks/use-runtime-override.ts`
- Create: `frontend/src/hooks/use-runtime-override-history.ts`
- Create: `frontend/src/components/runtime-workbench.tsx`
- Modify: `frontend/src/components/runtime-thread-panel.tsx`
- Modify: `frontend/src/hooks/use-runtime-thread.ts`
- Test: `frontend/tests/runtime-workbench.test.tsx`
- Test: `frontend/tests/runtime-thread-panel.test.tsx`

**Interfaces:**

- Consumes: runtime thread client, Task 4 override client, and task events.
- Produces: a single workbench owner for thread, context, history, refresh, and injected presentational state.

- [ ] **Step 1: Write RED orchestration tests**

Add `test_override_panel_eligible`, `test_override_panel_not_stable_disabled`, `test_override_panel_terminal_disabled`, and `test_override_permission`. Assert the initial render issues one thread read, one intervention-context read after thread identity is known, and one bounded history read. Assert no 200 ms timer is created.

- [ ] **Step 2: Run RED**

Run the two Task 5 test files and confirm missing workbench behavior.

- [ ] **Step 3: Implement shared ownership**

Move runtime-thread hook ownership into `RuntimeWorkbench`. Make `RuntimeThreadPanel` presentational for ready/loading/unauthorized/unavailable states. Add event classification so checkpoint/runtime-override events coalesce one refresh group. Preserve the existing feature gate.

- [ ] **Step 4: Run GREEN and existing lifecycle regression**

Run Task 5 tests and `frontend/tests/task-events-lifecycle.test.tsx`.

- [ ] **Step 5: REFACTOR**

Keep network state in hooks and rendering in components. Confirm `runtime-workbench.tsx` contains no `fetch`, WebSocket constructor, or mock import.

---

## Task 6: Confirm dialog, immutable snapshot, idempotency, and stale behavior

**Files:**

- Create: `frontend/src/components/runtime-override-dialog.tsx`
- Create: `frontend/src/features/runtime-override/dialog-snapshot.ts`
- Create: `frontend/src/features/runtime-override/error-copy.ts`
- Modify: `frontend/src/hooks/use-runtime-override.ts`
- Test: `frontend/tests/runtime-override-dialog.test.tsx`
- Test: `frontend/tests/runtime-override-hook.test.tsx`

**Interfaces:**

- Consumes: `RuntimeInterventionContext`, `RuntimeOverrideClient.create/get`, and relevant task events.
- Produces: `OverrideDialogSnapshot`, `isOverrideSnapshotStale`, submission state, stable idempotency retry, and exact error copy.

- [ ] **Step 1: Write dialog RED tests**

Add `test_override_dialog_shows_version` and `test_override_reason_required`. Assert vehicle, old/new value, captured version, next node, warning, and trimmed four-character validation are visible.

- [ ] **Step 2: Write hook RED tests**

Add:

- `test_override_submit_payload`
- `test_override_success_updates_version`
- `test_override_stale_dialog`
- `test_override_version_conflict_ui`
- `test_override_busy_ui`
- `test_override_partial_ui`

The payload assertion must prove refetched version N+1 does not replace the dialog's expected version N. Network retry must reuse the same mocked `crypto.randomUUID()` value. Closing and reopening must generate a different value.

- [ ] **Step 3: Run RED**

Run the two Task 6 test files and confirm absent dialog/state-machine failures.

- [ ] **Step 4: Implement minimal state machine**

Generate the key only on first Confirm. Preserve it in the attempt. Map domain codes exactly as specified. Implement stale comparison over version, checkpoint, next node, target entity/current value, and eligibility. For `PARTIAL`, schedule GET-only checks at 2, 4, and 8 seconds and stop correctly; never repeat POST.

- [ ] **Step 5: Run GREEN with fake timers**

Assert the partial sequence has at most three GETs and zero automatic extra POSTs.

- [ ] **Step 6: REFACTOR**

Keep error copy in a pure map and snapshot logic in a pure module. Re-run Task 6 tests after extraction.

---

## Task 7: Intervention panel, history, timeline, Capacity feedback, and audit

**Files:**

- Create: `frontend/src/components/runtime-intervention-panel.tsx`
- Create: `frontend/src/components/runtime-override-history.tsx`
- Create: `frontend/src/components/runtime-event-timeline.tsx`
- Create: `frontend/src/components/capacity-evidence-panel.tsx`
- Modify: `frontend/src/pages/api-dispatch-detail-page.tsx`
- Modify: `frontend/src/types/task-events.ts`
- Modify: `frontend/src/styles/index.css`
- Test: `frontend/tests/runtime-intervention-panel.test.tsx`
- Test: `frontend/tests/runtime-event-feedback.test.tsx`

**Interfaces:**

- Consumes: Task 5/6 state, bounded history, and existing ordered task events.
- Produces: visible field controls, success/conflict/partial result cards, safe audit history, timeline, Capacity evidence, and real routing/final feedback.

- [ ] **Step 1: Write panel/history RED tests**

Add `test_override_history` and assert only allowlisted action buttons exist. Assert no state-path, JSON, Pause, Resume, rollback, goto, skip, or rerun controls render.

- [ ] **Step 2: Write event-feedback RED tests**

Add `test_override_applied_event` and `test_capacity_displays_broken_vehicle`. Feed real-shaped task events and assert actor, reason, `NORMAL -> BROKEN`, version transition, `vehicle_available=false`, Capacity reason, routing decision, and `REVIEW_REQUIRED` are visible.

- [ ] **Step 3: Run RED**

Run Task 7 tests and confirm missing components/feedback.

- [ ] **Step 4: Implement accessible enterprise-console UI**

Place Runtime Thread then Runtime Intervention and history in the right column. Use red only for destructive target/risk, amber for stale/busy/partial, teal for applied, and text labels in addition to color. Use a focusable `role="dialog"`, labelled controls, disabled reasons, and an `aria-live` result message.

Render at most five history items collapsed and 30 timeline entries. Reuse the safe history DTO for the center audit entry. Do not render raw event JSON or checkpoint state.

- [ ] **Step 5: Run GREEN and visual regression checks**

Run Task 7 tests, all frontend tests, and the production build. Inspect 1440px and 1366px layouts in API mode; preserve the three-column behavior and existing theme.

- [ ] **Step 6: REFACTOR**

Extract repeated detail rows only when shared by at least two new components. Keep each file focused on one rendering responsibility.

---

## Task 8: Explicit mock-mode flow and API isolation

**Files:**

- Create: `frontend/src/mocks/runtime-override-data.ts`
- Create: `frontend/src/components/mock-runtime-intervention-workbench.tsx`
- Modify: `frontend/src/pages/dispatch-detail-page.tsx`
- Modify: `frontend/src/types/dispatch.ts`
- Test: `frontend/tests/runtime-override-mode-boundary.test.tsx`

**Interfaces:**

- Consumes: shared display types only.
- Produces: deterministic mock demonstration isolated from all HTTP/WebSocket clients.

- [ ] **Step 1: Write RED mode tests**

Add `test_api_mode_no_mock_override` and `test_mock_mode_override_isolated`. In API mode, fail the test if a mock module value is rendered after backend unavailability. In mock mode, fail if fetch or WebSocket is constructed.

- [ ] **Step 2: Run RED**

Run the Task 8 test and confirm the explicit mock workbench is absent.

- [ ] **Step 3: Implement isolated mock behavior**

Use one local `NORMAL -> BROKEN` demonstration with captured version 7 to 8 and mock audit history. Keep it under the existing `MockDispatchDetailPage`; do not route it through `HttpRuntimeOverrideClient`.

- [ ] **Step 4: Run GREEN and regression**

Run Task 8 plus existing `mock-service.test.ts` and `workspace-services.test.ts`.

---

## Task 9: Playwright and Docker browser harness

**Files:**

- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/support/api.ts`
- Create: `frontend/e2e/support/docker.ts`
- Create: `frontend/e2e/support/runtime-task.ts`
- Modify: `frontend/package.json`
- Modify: `docker-compose.yml`
- Create: `scripts/test-browser-e2e.ps1`
- Modify: `scripts/test-docker.ps1`
- Test: `backend/tests/unit/test_docker_runtime_files.py`

**Interfaces:**

- Consumes: existing nine-service Compose runtime and `.docker.env`.
- Produces: `npm run test:e2e`, deterministic worker pause/unpause helpers, seed IDs, health waits, auth-mode recreation, and cleanup.

- [ ] **Step 1: Write RED infrastructure assertions**

Extend the Docker file test to require the browser script, Playwright config, API-mode frontend arguments, parameterized `${RUNTIME_THREAD_AUTHORIZATION_PROVIDER:-trusted}`, and a `finally` restoration path in the script.

- [ ] **Step 2: Run RED**

Run the Docker runtime file unit test and confirm missing harness assertions fail.

- [ ] **Step 3: Implement Playwright config and helpers**

Configure Chromium, one retry in CI, trace on first retry, screenshots only on failure, base URL `http://localhost:5173`, API URL from `E2E_API_BASE_URL`, and serial execution for lifecycle-sensitive tests. Use `execFile`/PowerShell argument arrays for Docker commands; do not build shell command strings from task input.

- [ ] **Step 4: Implement robust PowerShell lifecycle**

The script must resolve Docker through the existing helper, validate exact service names, query the known seed IDs, set E2E environment values, pause/unpause only `worker-2`, switch backend auth mode only for the forbidden group, and restore trusted backend plus running workers in `finally`. It must fail if frontend is not API mode or if Pending is nonzero at the end.

- [ ] **Step 5: Run GREEN infrastructure checks**

Run the Docker file unit test and `npm exec playwright test -- --list` from `frontend` to prove test discovery without executing scenarios yet.

---

## Task 10: Real browser success and stale scenarios

**Files:**

- Create: `frontend/e2e/runtime-override-success.spec.ts`
- Create: `frontend/e2e/runtime-override-stale.spec.ts`

**Interfaces:**

- Consumes: Task 9 real task/Docker helpers and the V2-D2 UI.
- Produces: `test_browser_runtime_override_success` and `test_browser_runtime_override_stale`.

- [ ] **Step 1: Write success E2E before UI is considered complete**

Create a real task, open `/dispatch/{taskId}`, wait for `ELIGIBLE`, capture version/checkpoint, select `BROKEN`, fill `人工确认车辆爆胎`, confirm, and assert APPLIED plus exactly one version increment. Unpause worker continuation and assert Capacity shows BROKEN/unavailable and final status is REVIEW_REQUIRED.

- [ ] **Step 2: Run RED against Docker**

Run only the success spec. A failure is expected until all selectors, event payloads, and orchestration are correctly wired. Record the first behavior-level failure; do not weaken assertions.

- [ ] **Step 3: Apply the smallest integration fixes**

Fix only mismatches discovered between the implemented contract and real browser flow. Do not change D1 mutation semantics or force a routing result.

- [ ] **Step 4: Run success GREEN**

Repeat until the success scenario passes with real MySQL/Redis/checkpointer/worker evidence.

- [ ] **Step 5: Write and run stale E2E**

Open a dialog at version N, issue one competing valid override through Playwright's authenticated API context, wait for N+1, and assert the original dialog is STALE with disabled Confirm and still displays N. Confirm no second POST occurs.

---

## Task 11: Concurrent, forbidden, and terminal browser scenarios

**Files:**

- Create: `frontend/e2e/runtime-override-concurrent.spec.ts`
- Create: `frontend/e2e/runtime-override-forbidden.spec.ts`
- Create: `frontend/e2e/runtime-override-terminal.spec.ts`

**Interfaces:**

- Consumes: Task 9 lifecycle helpers.
- Produces: the remaining required real-browser acceptance tests.

- [ ] **Step 1: Write concurrent RED test**

Open two browser contexts on version N, choose BROKEN and MAINTENANCE, release Confirm concurrently, and assert one APPLIED plus one CONFLICT/BUSY. Query final thread/history and assert exactly one version increment and one APPLIED item.

- [ ] **Step 2: Run concurrent test to GREEN**

Fix only UI synchronization/selectors or safe read-contract issues. A test that accepts two APPLIED results is invalid.

- [ ] **Step 3: Write forbidden RED test**

Under fail-closed Docker backend authorization, assert the browser has no executable intervention button and a direct POST returns 403 with `RUNTIME_OVERRIDE_FORBIDDEN`.

- [ ] **Step 4: Run forbidden test to GREEN and restore auth**

Prove the runner restores trusted mode even after a failing assertion.

- [ ] **Step 5: Write terminal RED test**

Open a real completed task, assert eligibility `TERMINAL` and disabled actions, then direct POST with the captured terminal version and assert `THREAD_TERMINAL`.

- [ ] **Step 6: Run terminal test to GREEN**

Confirm the page shows the real final task/audit result and no mutation occurred.

---

## Task 12: Full regression, documentation, and acceptance evidence

**Files:**

- Modify: `docs/design.md`
- Create: `docs/verification/v2-d2-intervention-workbench-results.md`
- Create: `docs/verification/raw/v2-d2-browser-e2e.json`
- Modify: `README.md` only if the real browser command is not already discoverable elsewhere.

**Interfaces:**

- Consumes: all prior tasks and command output.
- Produces: reproducible V2-D2 acceptance evidence without overstated claims.

- [ ] **Step 1: Run backend quality gates**

```powershell
.venv\Scripts\python.exe -m ruff check backend scripts
.venv\Scripts\python.exe -m pytest backend -q
```

Record exact pass/skip counts and the reason for every skip.

- [ ] **Step 2: Run frontend quality gates**

```powershell
Set-Location frontend
npm run lint
npm test
npm run build
```

Record exact test counts and build result.

- [ ] **Step 3: Run real Docker and browser acceptance**

```powershell
Set-Location ..
scripts\test-docker.ps1
scripts\test-browser-e2e.ps1
```

Record all five named browser cases, real version/checkpoint transitions, Capacity status, final result, ordinary V1 result, nine-service health, and Pending count.

- [ ] **Step 4: Verify performance behavior**

Use Playwright request observation to report initial/refetch request counts and prove there is no 200 ms runtime poll. Re-run the existing Locust acceptance if backend read additions materially affect the normal dispatch API path; otherwise record that the normal endpoint implementation is unchanged and preserve the latest accepted measurements.

- [ ] **Step 5: Run safety scans**

Scan production sources and new evidence for secret-shaped values, raw authorization headers, checkpoint payload rendering, unbounded history, and disallowed controls. Fix every true positive.

- [ ] **Step 6: Update documentation from actual evidence**

Document only measured results. Include the HTTP/WebSocket truth boundary, stale behavior, permission mode, Docker orchestration, mock/API isolation, and deferred controls.

- [ ] **Step 7: Final verification**

```powershell
scripts\check.ps1
git diff --check
git diff --stat
git status --short
```

Inspect the complete diff. Do not stage, commit, merge, or create a PR unless explicitly requested.

## Required final evidence

The completion report must state:

1. Workbench placement and real API mode.
2. Eligibility and permission behavior.
3. Immutable dialog snapshot and stale proof.
4. Stable idempotency retry behavior.
5. APPLIED, conflict, busy, rejected, partial, and failure UX.
6. Safe override history and audit display.
7. Override and Capacity event evidence.
8. Capacity consuming the overridden status.
9. Real final routing/task result.
10. Five Playwright scenario outcomes.
11. Backend/frontend exact test counts.
12. Nine-service Docker health and Redis Pending.
13. Ordinary no-override V1 regression.
14. Confirmation that D1 core semantics were not redesigned.
15. Confirmation that V2-D3 or other deferred controls were not implemented.
