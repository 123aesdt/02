# CountyFlow V2-D2 Runtime Intervention Workbench Design

**Date:** 2026-08-27

**Status:** Design ready for approval

**Scope:** Runtime Intervention Workbench, safe browser interaction, task-event feedback, audit presentation, and real Docker Playwright acceptance
**Prerequisite:** V2-A, V2-B, V2-C, and V2-D1 are complete

## 1. Goal and non-goals

V2-D2 makes the V2-D1 safe-boundary runtime override usable by a dispatch supervisor on the existing dispatch detail page. The browser must display the canonical runtime boundary, permission, vehicle state, allowed actions, result, downstream Capacity evidence, and durable override audit history. Formal acceptance runs in API mode against the real nine-service Docker runtime.

V2-D2 does not redesign the V2-D1 command path. Redis locking, MySQL boundary CAS, official LangGraph `aupdate_state`, checkpoint validation, canonical promotion, orphan isolation, idempotency, and reconciliation remain unchanged. This phase also does not add pause, resume, rollback, target-node selection, node skipping, node rerun, arbitrary state paths, JSON Patch, or `BROKEN -> NORMAL`.

## 2. Existing baseline and observed contract gaps

The existing page route is `/dispatch/:taskId`. In API mode, `ApiDispatchDetailPage` already owns task status/result and the task-event WebSocket. `RuntimeThreadPanel` reads the canonical runtime thread and a bounded checkpoint history. The page already presents the eight-agent pipeline, vector evidence, graph evidence, routing, dispatch, and final audit.

The V2-D1 write endpoint already accepts the required preconditions and returns an auditable override result. Four read/event gaps must be closed without changing the write algorithm:

1. Runtime-thread reads expose state and boundary metadata but do not expose authoritative intervention eligibility or effective override permission.
2. Override detail exists, but the API has no implemented bounded list by thread for history and audit UI.
3. Override events omit actor and reason, and non-APPLIED status events have a publisher but are not yet delivered through the complete request path.
4. `CAPACITY_COMPLETED` currently carries no safe capacity summary, so the browser cannot prove that Capacity consumed the overridden `vehicle_status`.

These are read DTO and event DTO/integration changes only. They do not alter D1 state mutation, lock order, CAS predicates, or promotion semantics.

## 3. Approaches considered

### 3.1 Recommended: server eligibility read model plus a frontend state machine

The backend builds a bounded `RuntimeInterventionContext` from the canonical MySQL thread pointer, exact Redis checkpoint, and authorization result. The frontend renders that result and maintains only interaction state: dialog snapshot, reason validation, idempotency key, submission status, and stale detection.

This keeps safety policy authoritative on the server, avoids duplicating boundary logic in React, and gives browser tests a stable contract. It adds one focused query service and does not touch the override command algorithm.

### 3.2 Rejected: derive eligibility entirely in React

The browser could infer eligibility from `status`, `current_node`, `next_node`, and raw checkpoint state. It still cannot know effective `runtime:override` permission, and policy drift would allow the UI to advertise an action the server rejects. This approach is rejected.

### 3.3 Rejected: create a separate intervention administration application

A dedicated admin route would duplicate task context, runtime timeline, WebSocket ownership, and audit display. It would also expand navigation and authorization scope. V2-D2 stays inside the dispatch detail workspace.

## 4. Workbench placement and component boundary

The existing three-column dispatch detail remains intact:

```text
Left context                  Center evidence/result             Right runtime
---------------------------   -------------------------------    ---------------------------
Task / anomaly                Environment and memory evidence    Runtime Thread
Vehicle / route               Capacity feedback                 Runtime Intervention
                              Routing / dispatch                 Override History
                              Final audit + intervention audit   Agent / Runtime Timeline
```

`RuntimeWorkbench` becomes the right-column container for canonical thread data. It owns `useRuntimeThread`, `useRuntimeInterventionContext`, and `useRuntimeOverrideHistory`, then renders focused presentational components:

- `RuntimeThreadPanel`: thread identity, status, canonical pointer, nodes, version, and checkpoint history.
- `RuntimeInterventionPanel`: eligibility, current vehicle/status, allowed actions, permission, and latest result.
- `RuntimeOverrideDialog`: immutable snapshot, target status, reason, risk text, and confirmation.
- `RuntimeOverrideHistory`: bounded safe history.
- `RuntimeEventTimeline`: task/agent/runtime events ordered by server sequence.

`ApiDispatchDetailPage` remains the composition root. It passes task events to the workbench and uses the same event collection for Capacity and Routing feedback. Page components never call `fetch` directly.

The mock route keeps a separate `MockRuntimeInterventionWorkbench`; it does not instantiate HTTP clients. API mode never imports or falls back to mock override data.

## 5. Authoritative intervention context

Add the read-only endpoint:

```http
GET /api/v1/runtime/threads/{thread_id}/intervention
```

Response:

```json
{
  "thread_id": "cf:dispatch:TASK-...",
  "task_id": "TASK-...",
  "runtime_status": "STABLE",
  "state_version": 7,
  "current_node": "environment",
  "next_node": "capacity",
  "canonical_checkpoint_id": "checkpoint-7",
  "checkpoint_available": true,
  "eligibility": "ELIGIBLE",
  "eligibility_reason_code": null,
  "can_override": true,
  "target": {
    "entity_type": "Vehicle",
    "entity_id": "vehicle-001",
    "display_name": "vehicle-001",
    "field": "status",
    "current_value": "NORMAL",
    "allowed_new_values": ["BROKEN", "UNAVAILABLE", "MAINTENANCE"]
  },
  "observed_at": "2026-08-27T14:03:01Z"
}
```

`display_name` uses a real business display name when one is already present in canonical state; otherwise it equals `entity_id`. The server does not invent a vehicle name.

`RuntimeInterventionQueryService` is a read-side service. It depends on the runtime-thread repository, exact checkpoint store, override query repository, and existing authorizer. No driver/session/repository enters frontend state or LangGraph state.

### 5.1 Eligibility precedence

The server returns exactly one of:

| Eligibility | Condition | UI action |
| --- | --- | --- |
| `NO_PERMISSION` | Caller may read the thread but lacks `runtime:override` | Hide action group or render it disabled with an explicit permission message |
| `TERMINAL` | Thread status is `TERMINAL` | Disable actions; explain that completed tasks cannot be changed |
| `BUSY` | Thread status is `OVERRIDING` | Disable actions; explain that another intervention/reconciliation owns the boundary |
| `NOT_STABLE` | Thread status is `RUNNING` or any non-stable executable state | Disable actions; explain that an agent is executing |
| `WRONG_BOUNDARY` | Stable but not `environment -> capacity`, the canonical pointer/record or target is missing, or current status is not `NORMAL` | Disable actions and display the specific safe reason code |
| `ELIGIBLE` | Permission exists; status is `STABLE`; exact boundary is `environment -> capacity`; checkpoint exists; vehicle matches canonical state; status is `NORMAL` | Enable the three allowlisted actions |

Permission is checked before revealing executable controls. A caller with `runtime:read` but without `runtime:override` receives `NO_PERMISSION`; a caller without read permission receives HTTP 403 and no context.

An exact-checkpoint lookup transport failure returns HTTP 503 rather than pretending the boundary is eligible or absent. The eligibility read is advisory for interaction only. POST repeats all D1 authorization, lock, version, boundary, entity, old-value, and target-value checks.

## 6. Field controls

The workbench exposes one target:

- Entity: `Vehicle`
- Field: `status`
- Current value: `NORMAL`
- New value: `BROKEN`, `UNAVAILABLE`, or `MAINTENANCE`

The browser renders three explicit buttons. There is no free-form entity type, entity ID, field name, state path, target node, or JSON editor. Allowed values come from the backend read model and are also intersected with the compile-time TypeScript union. Any unknown server value is ignored and no action is enabled.

## 7. Confirm dialog and immutable version snapshot

Selecting a target opens a modal dialog with:

- Vehicle display name and entity ID.
- Current value and selected new value.
- Thread state version.
- Current and next node.
- Canonical checkpoint ID.
- Required reason field.
- A warning that canonical LangGraph runtime state will change and Capacity will consume the new status.

The reason is trimmed and must contain at least four characters in the browser. The backend remains the final validator and retains its bounded request validation.

At dialog open, the frontend copies an immutable `OverrideDialogSnapshot`:

```ts
interface OverrideDialogSnapshot {
  threadId: string;
  taskId: string;
  checkpointId: string;
  expectedVersion: number;
  expectedNextNode: "capacity";
  entityType: "Vehicle";
  entityId: string;
  field: "status";
  oldValue: "NORMAL";
  newValue: "BROKEN" | "UNAVAILABLE" | "MAINTENANCE";
}
```

The submit payload is built only from this snapshot plus the reason and current attempt idempotency key. A background refetch may update the page, but it never replaces dialog preconditions.

## 8. Stale dialog behavior

Task events that can change the canonical boundary trigger one coalesced runtime refetch: `THREAD_CHECKPOINTED`, `THREAD_RESUMED`, `THREAD_TERMINAL`, and every `RUNTIME_OVERRIDE_*` event. The dialog becomes `STALE` when any of these differ from its snapshot:

- `state_version`
- canonical checkpoint ID
- `next_node`
- target entity ID
- target current value
- eligibility no longer equals `ELIGIBLE`

The dialog keeps showing both the captured version and the newly observed version. Confirm is disabled and the user must close, refresh, and choose a new action. If the server wins the race before the refetch arrives, the POST conflict response produces the same conflict UX. There is no silent rebase.

## 9. Idempotency lifecycle

The first press of Confirm generates `runtime-override:<UUID>` with `crypto.randomUUID()` and stores it in the current attempt. The same key is retained across timeout, network retry, and a safe `GET /runtime/overrides/{override_id}` status check. The key is never regenerated automatically after `PARTIAL`.

Closing the dialog and starting a genuinely new operation clears the attempt and generates a new key on the next Confirm. Changing the target before the first submission does not create a command.

## 10. Submission state machine and HTTP error UX

Frontend state is one of `IDLE`, `SUBMITTING`, `APPLIED`, `CONFLICT`, `BUSY`, `REJECTED`, `PARTIAL`, or `FAILED`.

| HTTP/result | Frontend state | User message |
| --- | --- | --- |
| `APPLIED` | `APPLIED` | Show `Vehicle: NORMAL -> new`, version transition, and success time |
| 403 `RUNTIME_OVERRIDE_FORBIDDEN` | `REJECTED` | No permission to perform runtime intervention |
| 409 `RUNTIME_STATE_VERSION_CONFLICT` | `CONFLICT` | Runtime state changed; refresh and select again |
| 409 `RUNTIME_OVERRIDE_BUSY` | `BUSY` | Another operation is modifying this thread |
| 409 `THREAD_NOT_STABLE` | `BUSY` | An agent is executing; intervention is temporarily unavailable |
| 409 `THREAD_TERMINAL` | `REJECTED` | The task has ended and cannot be changed |
| 409/422 `RUNTIME_STATE_PRECONDITION_FAILED` | `CONFLICT` | Canonical state no longer matches the captured dialog |
| 422 `OVERRIDE_FIELD_NOT_ALLOWED` or `OVERRIDE_VALUE_INVALID` | `REJECTED` | This state transition is not allowed |
| 503 `CHECKPOINT_STORE_UNAVAILABLE` | `FAILED` | Runtime state storage is unavailable; retry with the same key |
| HTTP 202 or body status `PARTIAL` | `PARTIAL` | Modification is being recovered; do not submit a new intervention |
| network timeout/offline | `FAILED` | Outcome is uncertain; retry the same attempt key or query the known override ID |

The shared API client preserves structured backend error codes for 422 responses. It only uses `VALIDATION_ERROR` when FastAPI returns field-validation details without a domain code.

`PARTIAL` starts bounded read-only reconciliation observation: GET the same override after 2, 4, and 8 seconds, stopping on a final status, an applicable WebSocket event, unmount, or the third attempt. It never repeats POST. If still partial, the UI remains visibly partial and offers status refresh, not a new override.

## 11. HTTP truth and WebSocket notification

HTTP POST and subsequent GET responses are the business truth. WebSocket is a real-time notification and refresh trigger.

After `APPLIED`, the UI:

1. Completes and closes the dialog.
2. Displays the vehicle and version diff.
3. Refetches intervention context and runtime thread.
4. Refetches bounded override history.
5. Waits for or consumes `RUNTIME_OVERRIDE_APPLIED` without treating a missing event as failure.
6. Continues to observe normal Worker events; no Resume button is shown.

## 12. Override history and audit display

Add the bounded endpoint on the same collection URI as POST:

```http
GET /api/v1/runtime/threads/{thread_id}/overrides?limit=20
```

It returns newest-first items and a fixed maximum of 100. Each item contains only:

- override ID and timestamps
- actor ID and role
- entity ID/type and field
- old/new values
- reason
- status, decision, event status, and safe error code
- expected, before, and after state versions
- source and result checkpoint IDs

It excludes idempotency key, payload fingerprint, raw authorization material, tokens, timing internals, and checkpoint state/payload.

The right column shows the latest five records by default with an expansion to the bounded list. The center audit area shows the same APPLIED record as an intervention audit entry beside the final dispatch audit. There is no second source of audit truth.

Existing `GET /api/v1/runtime/overrides/{override_id}` is routed through the authenticated query service so detail and history enforce the same read authorization.

## 13. Event contract and runtime timeline

The existing task-event stream remains the single browser channel. The following safe payloads are required:

| Event | Required safe data |
| --- | --- |
| `RUNTIME_OVERRIDE_REQUESTED` | override ID, thread ID, actor ID/role, entity/field, old/new, reason, expected version/next node |
| `RUNTIME_OVERRIDE_APPLIED` | the requested fields plus source/result checkpoint and before/after version |
| `RUNTIME_OVERRIDE_REJECTED` | safe request summary, status, and error code |
| `RUNTIME_OVERRIDE_CONFLICT` | safe request summary, status, and error code |
| `RUNTIME_OVERRIDE_PARTIAL` | override ID, source/result checkpoint, versions, and recovery-required error code |
| `CAPACITY_COMPLETED` | vehicle ID, canonical vehicle status, driver/vehicle availability, capacity status, risk level, and safe reason |
| `ROUTING_COMPLETED` | recommended route, decision, memory adopted, and adopted memory ID when present |

Reason is already bounded by the command schema. Events never include raw authorization headers, tokens, idempotency keys, full checkpoint payloads, or exception text.

Activating the already-defined non-APPLIED event publisher is an event delivery completion, not a change to D1 write semantics. Event publication failure never changes an HTTP `APPLIED` result or canonical state.

`RuntimeEventTimeline` sorts accepted events by server `sequence`, deduplicates by `event_id`, and renders at most 30 entries. Override rows show actor and field diff; checkpoint rows show version/pointer summary; Capacity rows show the consumed status and availability. Reconnect continues from `last_event_id` using the existing client.

## 14. Capacity, routing, and final-result feedback

`CapacityEvidencePanel` reads the latest real `CAPACITY_COMPLETED` event. After an override it must visibly show:

- `Vehicle vehicle-001`
- `Runtime status BROKEN` (or selected target)
- `vehicle_available = false`
- Capacity status and reason

The graph state remains the source used by Capacity. The UI never derives availability from the selected button.

Routing remains unaware of override mechanics and receives ordinary Capacity output. The page displays the real `ROUTING_COMPLETED` event and the final task/result response. If the overridden vehicle makes the task `REVIEW_REQUIRED`, the browser displays that result. The workbench does not force `REROUTE` for the intervention demo.

The no-override regression remains `memory-rain-li -> national-102 -> REROUTE -> APPROVED`, with Redis Pending equal to zero.

## 15. Mock/API isolation

`VITE_DATA_MODE=mock` uses explicit in-memory workbench data with the same public types and a deterministic demo transition. It does not call WebSocket or backend clients.

`VITE_DATA_MODE=api` uses only `HttpRuntimeOverrideClient`, `HttpRuntimeThreadClient`, and the existing `TaskEventClient`. A missing, forbidden, offline, or ineligible backend state renders an unavailable/disabled state. API mode never substitutes mock eligibility, history, events, or success results.

The Docker frontend remains built with `VITE_DATA_MODE=api`, `VITE_API_BASE_URL=http://localhost:8001`, and runtime-thread state enabled.

## 16. Frontend data layer

Add exact backend-aligned types in `frontend/src/types/runtime-override.ts`:

- `RuntimeOverrideRequest`
- `RuntimeOverrideResponse`
- `RuntimeOverrideDetail`
- `RuntimeOverrideStatus`
- `RuntimeInterventionEligibility`
- `RuntimeInterventionContext`
- `RuntimeOverrideHistory`
- `OverrideSubmissionState`

`RuntimeOverrideClient` exposes:

```ts
interface RuntimeOverrideClient {
  getInterventionContext(threadId: string, signal?: AbortSignal): Promise<RuntimeInterventionContext>;
  create(threadId: string, request: RuntimeOverrideRequest, signal?: AbortSignal): Promise<RuntimeOverrideResponse>;
  get(overrideId: string, signal?: AbortSignal): Promise<RuntimeOverrideDetail>;
  listByThread(threadId: string, limit: number, signal?: AbortSignal): Promise<RuntimeOverrideHistory>;
}
```

`useRuntimeOverride` owns dialog snapshot, reason, idempotency key, stale calculation, submit/retry, result, and domain-error mapping. `useRuntimeOverrideHistory` owns bounded history loading and event-triggered refetch. Components receive these hooks or injected clients; they do not perform direct network calls.

## 17. Browser E2E architecture

Playwright is already installed but not configured. Add `frontend/playwright.config.ts`, `frontend/e2e/`, and an explicit `npm run test:e2e` script. Formal tests use Chromium against `http://localhost:5173` and API `http://localhost:8001`.

`scripts/test-browser-e2e.ps1` is the orchestration entry point. It:

1. Verifies `.docker.env`, nine healthy services, API mode frontend, Redis, MySQL, and the checkpoint backend.
2. Reads only the known seed order/anomaly IDs from MySQL for task setup.
3. Pauses `worker-2` only for tests that require the Environment stable window; `worker-1` remains the interrupting worker.
4. Runs success, stale, and concurrent tests while the boundary is held.
5. Unpauses `worker-2` and proves Capacity/final completion.
6. Runs terminal behavior against a completed task.
7. Recreates only the backend with `RUNTIME_THREAD_AUTHORIZATION_PROVIDER=disabled` for the forbidden browser/direct-POST test, then restores `trusted` in a `finally` block.
8. Confirms Redis Pending is zero and leaves the normal nine-service runtime healthy.

No product pause/resume endpoint is added. Docker pause/unpause is test orchestration outside the application.

### 17.1 Success scenario

The browser opens the real task, waits for `STABLE`, `environment -> capacity`, and `ELIGIBLE`, opens the dialog, selects `BROKEN`, enters `人工确认车辆爆胎`, confirms, and asserts:

- POST returns/rendered status `APPLIED`.
- state version increments by exactly one.
- canonical checkpoint changes.
- history shows actor, reason, `NORMAL -> BROKEN`, and version transition.
- after worker continuation, Capacity displays `BROKEN` and unavailable.
- final status is the real safe result, expected to be `REVIEW_REQUIRED` for the seeded scenario.

### 17.2 Stale dialog

The browser opens a dialog at version N. A test-side authenticated API request applies a competing valid override using version N. WebSocket/refetch observes version N+1; the open dialog displays `STALE`, preserves N, and disables Confirm. It never changes its payload to N+1.

### 17.3 Concurrent browsers

Two isolated browser contexts open the same version and select different allowed target values. Their Confirm requests are released concurrently. Exactly one renders `APPLIED`; the other renders `CONFLICT` or `BUSY`. A final thread/history read proves one canonical version increment and one APPLIED transition.

### 17.4 Permission and terminal cases

With the Docker backend in fail-closed authorization mode, the browser hides/disables intervention and a direct POST receives 403. With a terminal task under normal authorization, eligibility is `TERMINAL`, actions are disabled, and direct POST returns `THREAD_TERMINAL`.

## 18. Performance and refresh policy

V2-D2 adds no continuous runtime-thread polling. Refreshes are coalesced per animation frame/microtask when multiple relevant events arrive together. Normal behavior is:

- initial thread/context/history GET once;
- one refetch group after an applicable WebSocket event;
- one refetch group after POST;
- bounded 2/4/8-second GET detail observation only for `PARTIAL`;
- existing one-second task-status polling remains unchanged until terminal.

History is capped at 20 by the client and 100 by the server. Timeline rendering is capped at 30. Browser acceptance records request counts and fails if the workbench issues a 200 ms polling pattern.

## 19. Test strategy

### 19.1 Backend behavior tests

- context returns `ELIGIBLE` only at canonical `environment -> capacity` with permission and `NORMAL` vehicle status;
- `NOT_STABLE`, `TERMINAL`, `NO_PERMISSION`, `WRONG_BOUNDARY`, and `BUSY` precedence;
- exact-checkpoint unavailable maps safely;
- history is newest-first, bounded, authorized, and excludes secrets/payloads;
- override requested/applied/rejected/conflict/partial events carry safe required fields and publish once;
- Capacity completion includes the canonical overridden status and availability;
- D1 write-service tests remain unchanged and green.

### 19.2 Frontend component/hook tests

The implementation must include these named tests:

- `test_override_panel_eligible`
- `test_override_panel_not_stable_disabled`
- `test_override_panel_terminal_disabled`
- `test_override_permission`
- `test_override_dialog_shows_version`
- `test_override_reason_required`
- `test_override_submit_payload`
- `test_override_success_updates_version`
- `test_override_stale_dialog`
- `test_override_version_conflict_ui`
- `test_override_busy_ui`
- `test_override_partial_ui`
- `test_override_applied_event`
- `test_override_history`
- `test_capacity_displays_broken_vehicle`
- `test_api_mode_no_mock_override`
- `test_mock_mode_override_isolated`

Tests assert visible behavior and exact request payloads rather than component internals.

### 19.3 Real browser tests

- `test_browser_runtime_override_success`
- `test_browser_runtime_override_stale`
- `test_browser_runtime_override_concurrent`
- `test_browser_runtime_override_forbidden`
- `test_browser_runtime_override_terminal`

The browser suite uses real Docker Redis, MySQL, AsyncRedisSaver, backend, workers, and V2-D1 override. It does not use frontend mock data, fakeredis, or SQLite.

### 19.4 Regression gates

- backend Ruff and full pytest;
- frontend ESLint, Vitest, and production build;
- real Docker V2-A/V2-B/V2-C/V2-D1 acceptance;
- real Playwright V2-D2 suite;
- ordinary V1 scenario remains `memory-rain-li -> national-102 -> REROUTE -> APPROVED`;
- intervention scenario exposes the real Capacity outcome and safe final result;
- Redis Pending equals zero;
- `git diff --check` and secret/placeholder scans.

## 20. Deferred controls

The following remain outside V2-D2:

- generic Pause or manual Resume;
- rollback or historical checkpoint selection;
- goto/skip/rerun/target-node controls;
- arbitrary entity, field, state path, JSON, or patch input;
- `BROKEN -> NORMAL` or any reverse transition;
- routing-algorithm awareness of runtime override;
- automatic shared-memory/Qdrant/Neo4j mutation;
- a separate intervention administration application;
- broad production identity-provider implementation beyond consuming the existing external authorizer contract.

## 21. Acceptance boundary

V2-D2 is complete only when the supervisor can perform the seeded override through the API-mode browser, observe the canonical version transition, see Capacity consume the new status, see the real final safe result, and retrieve a bounded audit history; all stale, concurrent, forbidden, terminal, and partial behaviors must remain explicit and safe. D1 invariants and the ordinary no-override V1 outcome must not regress.
