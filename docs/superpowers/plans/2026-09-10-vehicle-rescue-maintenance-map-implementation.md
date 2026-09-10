# Vehicle Rescue, Maintenance, and Map Command Center Implementation Plan

> **Execution mode:** Inline execution in this session. The written design in `docs/superpowers/specs/2026-09-10-vehicle-rescue-maintenance-map-system-design.md` and V8 visual baseline are already approved by the user.

**Goal:** Turn vehicle breakdown handling into a complete, restart-safe workflow that dispatches replacement capacity, rescues and tows the failed vehicle, advances maintenance automatically, performs safety inspection, restores eligible vehicles to the available fleet, and exposes the whole process in the V8 map command center.

**Architecture:** Keep the existing asynchronous dispatch path. The dispatch worker invokes a narrow vehicle-operations orchestration interface only after the dispatch decision is durably approved. MySQL remains the source of truth for vehicle state, rescue missions, maintenance orders, transition history, and outbox events. A restart-safe progressor claims due rows with row locking and advances one transition per claim. Read APIs compose one map snapshot from road-network topology and vehicle-operation records. The React page polls the snapshot and consumes task WebSocket events without inventing route geometry.

**Tech stack:** FastAPI, Pydantic, SQLAlchemy 2, Alembic, MySQL/SQLite tests, Redis task events, pytest, React 18, TypeScript, Vitest, Lucide, CSS/SVG functional vector map.

---

## Task 1: Domain states and persistence schema

**Files:**

- Create: `backend/app/vehicle_operations/models.py`
- Create: `backend/app/models/vehicle_operation.py`
- Modify: `backend/app/models/fleet_vehicle.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260910_15_vehicle_rescue_maintenance.py`
- Create: `backend/tests/vehicle_operations/test_domain.py`
- Create: `backend/tests/migrations/test_vehicle_rescue_maintenance_migration.py`

**TDD steps:**

1. Add failing tests for every allowed and rejected vehicle, rescue-mission, and maintenance-order transition.
2. Run `pytest backend/tests/vehicle_operations/test_domain.py -q` and confirm the missing-domain failure.
3. Implement enums, immutable snapshots, transition policies, `Clock`, and domain errors.
4. Add failing migration-model tests for enhanced vehicle columns and the five new tables.
5. Run `pytest backend/tests/migrations/test_vehicle_rescue_maintenance_migration.py backend/tests/unit/test_models.py -q` and confirm failures.
6. Implement ORM rows and Alembic revision:
   - enhanced `fleet_vehicles`: `fault_code`, `status_reason`, `status_changed_at`, `available_after`, `maintenance_order_no`;
   - `rescue_units`;
   - `rescue_missions`;
   - `maintenance_bays`;
   - `maintenance_orders`;
   - `vehicle_status_history`;
   - `domain_outbox`.
7. Use `version_id_col` on mutable rescue, maintenance, bay, and vehicle rows.
8. Re-run both targeted suites until green.
9. Run `git diff --check` and inspect the phase diff.
10. Commit: `feat: add vehicle rescue and maintenance domain schema`.

## Task 2: SQL repositories, vehicle transitions, and outbox

**Files:**

- Create: `backend/app/vehicle_operations/protocols.py`
- Create: `backend/app/vehicle_operations/sqlalchemy_repository.py`
- Create: `backend/app/vehicle_operations/outbox.py`
- Modify: `backend/app/fleet/protocols.py`
- Modify: `backend/app/fleet/sqlalchemy_repository.py`
- Create: `backend/tests/vehicle_operations/test_sqlalchemy_repository.py`
- Create: `backend/tests/concurrency/test_vehicle_operation_claims.py`

**Interfaces:**

- `VehicleService.transition(vehicle_id, expected_status, target_status, reason, task_id)`
- `VehicleOperationsRepository.create_breakdown_case(...)`
- `VehicleOperationsRepository.claim_due_rescue(now, limit)`
- `VehicleOperationsRepository.claim_due_maintenance(now, limit)`
- `VehicleOperationsRepository.advance_rescue(...)`
- `VehicleOperationsRepository.advance_maintenance(...)`
- `VehicleOperationsRepository.record_inspection(...)`
- `OutboxWriter.append(aggregate_type, aggregate_id, event_type, payload)`

**TDD steps:**

1. Add failing repository tests covering atomic create, history, outbox, duplicate task idempotency, and optimistic-lock conflicts.
2. Add a failing concurrency test proving two sessions cannot advance the same due item twice.
3. Run the tests and retain the real failure output.
4. Implement repository methods with one transaction boundary per command, `SELECT ... FOR UPDATE` and `SKIP LOCKED` when supported.
5. Translate `StaleDataError` into the existing `OptimisticLockConflict` family instead of comparing versions in Python.
6. Re-run targeted repository and concurrency tests.
7. Run `git diff --check`, inspect diff, and commit: `feat: persist rescue workflow with transactional outbox`.

## Task 3: Fault orchestration and topology-backed route planning

**Files:**

- Create: `backend/app/vehicle_operations/service.py`
- Create: `backend/app/vehicle_operations/routing.py`
- Modify: `backend/app/road_network/protocols.py`
- Modify: `backend/app/fleet/service.py`
- Create: `backend/tests/vehicle_operations/test_orchestration_service.py`
- Create: `backend/tests/vehicle_operations/test_routing.py`

**Behavior:**

- On an approved `VEHICLE_BREAKDOWN`, stop the vehicle safely, allocate a compatible replacement vehicle and driver, reserve the replacement, transfer cargo responsibility, calculate replacement/rescue/tow paths from the persisted road graph, create one rescue mission and one maintenance order, and persist outbox events within the same database transaction.
- Route results store only ordered `edge_ids` backed by `road_edges`; no freehand map route is accepted.
- Severe cold-chain, brake, steering, accident, or injury cases are marked manual-inspection-required.

**TDD steps:**

1. Add failing behavior tests for a normal cold-chain breakdown, no replacement available, unreachable rescue, repeated orchestration, and route-edge provenance.
2. Run targeted tests and confirm failures.
3. Implement `RescueOrchestrationService` using `FleetProvider`, `FleetAllocationService`, `RoutingService`/`PathFinder`, and the repository protocol only.
4. Keep external-provider timeout/fallback behavior behind existing route-provider boundaries.
5. Re-run tests and inspect `git diff`.
6. Commit: `feat: orchestrate replacement rescue and tow routes`.

## Task 4: Automatic rescue, maintenance, inspection, and recovery

**Files:**

- Create: `backend/app/vehicle_operations/progressor.py`
- Create: `backend/app/vehicle_operations/inspection.py`
- Create: `backend/app/workers/vehicle_operations_worker.py`
- Modify: `backend/app/core/config.py`
- Create: `backend/tests/vehicle_operations/test_progressor.py`
- Create: `backend/tests/workers/test_vehicle_operations_worker.py`
- Create: `backend/tests/integration/test_real_vehicle_operation_progression.py`

**Behavior:**

- `RescueProgressor`: `DISPATCHED -> ARRIVED -> LOADED -> DELIVERED`.
- `MaintenanceProgressor`: `SCHEDULED -> WAITING_BAY -> DIAGNOSING -> REPAIRING -> QA_PENDING -> COMPLETED`.
- Vehicle: `WAITING_RESCUE -> IN_RESCUE -> MAINTENANCE -> QA_PENDING -> AVAILABLE`; failed/manual QA produces `OUT_OF_SERVICE` until authorized reopening.
- Each claim advances only one transition. Due timestamps and version columns make restarts harmless.
- Development demo uses configurable time scale `120`; stored business durations remain real values.

**TDD steps:**

1. Add failing clock-driven tests for all automatic transitions, QA pass/fail, one-step-per-claim, restart, cancellation, and dual worker execution.
2. Run tests and confirm red.
3. Implement deterministic `SafetyInspectionService`, progressors, and a cancellation-safe periodic worker.
4. Add configuration for time scale, polling interval, and batch size.
5. Run unit tests, then the targeted real-MySQL integration test against Docker.
6. Inspect `git diff --check` and commit: `feat: auto progress rescue maintenance and fleet recovery`.

## Task 5: Query model and HTTP APIs

**Files:**

- Create: `backend/app/vehicle_operations/query_service.py`
- Create: `backend/app/api/v1/vehicle_operations.py`
- Create: `backend/app/api/v1/vehicle_operation_schemas.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/security/permissions.py` only if an existing permission cannot express the action.
- Create: `backend/tests/api/test_vehicle_operations.py`
- Create: `backend/tests/vehicle_operations/test_map_snapshot_query.py`

**Endpoints:**

- `GET /api/v1/map/snapshot?task_id=...`
- `GET /api/v1/fleet/vehicles`
- `GET /api/v1/rescue-missions/{mission_no}`
- `POST /api/v1/rescue-missions/{mission_no}/retry`
- `GET /api/v1/maintenance-orders`
- `GET /api/v1/maintenance-orders/{order_no}`
- `POST /api/v1/maintenance-orders/{order_no}/inspection-decisions`

**TDD steps:**

1. Add failing API tests for authorization, schemas, 404/409/422 cases, and map topology/route evidence.
2. Run the API tests and confirm red.
3. Implement Pydantic schemas, query service, router, exception translation, and `create_app` dependency injection.
4. Ensure the map snapshot includes nodes, edges, vehicle markers, replacement path, rescue path, tow path, incident metadata, rescue progress, maintenance progress, countdown, and ordered event timeline.
5. Re-run API and query tests.
6. Inspect diff and commit: `feat: expose vehicle operations and map snapshot APIs`.

## Task 6: Async dispatch and event integration

**Files:**

- Modify: `backend/app/events/models.py`
- Modify: `backend/app/workers/dispatch_worker.py`
- Modify: `backend/app/runtime.py`
- Modify: `backend/app/main.py`
- Create: `backend/app/vehicle_operations/events.py`
- Modify: `backend/tests/workers/test_dispatch_worker.py`
- Create: `backend/tests/vehicle_operations/test_events.py`

**TDD steps:**

1. Add failing worker tests proving orchestration runs only after a durable approved dispatch, does not run for non-breakdown events, and repeated delivery stays idempotent.
2. Add failing event tests for rescue/maintenance/status event payloads.
3. Run targeted tests and confirm red.
4. Wire the orchestration interface into the worker and publish outbox events through the existing task-event broker.
5. Start/stop the operations progressor with application lifecycle; make shutdown cancellation-safe.
6. Re-run worker/event/API tests.
7. Inspect diff and commit: `feat: connect dispatch worker to rescue lifecycle`.

## Task 7: V8 map command center frontend

**Files:**

- Create: `frontend/src/types/vehicle-operations.ts`
- Create: `frontend/src/services/api/vehicle-operations-client.ts`
- Create: `frontend/src/hooks/use-vehicle-operation-snapshot.ts`
- Rewrite: `frontend/src/pages/fleet-live-map-page.tsx`
- Rewrite: `frontend/src/components/fleet-sandbox-map.tsx`
- Create: `frontend/src/components/vehicle-operation-panel.tsx`
- Create: `frontend/src/features/fleet-sandbox/operation-map-geometry.ts`
- Create: `frontend/src/styles/vehicle-command-center.css`
- Modify: `frontend/src/styles/index.css`
- Modify: `frontend/src/main.tsx`
- Create: `frontend/tests/vehicle-operations-client.test.ts`
- Rewrite: `frontend/tests/fleet-live-map-page.test.tsx`
- Create: `frontend/tests/vehicle-operation-panel.test.tsx`
- Modify: `frontend/tests/responsive-accessibility.test.ts`

**Visual/interaction contract:**

- Match the 1440x900 V8 baseline: dark-teal sidebar, compact top bar, 2-column command surface, top tabs, AMap-like light county map, right four-stage incident panel, and bottom event rail.
- The functional SVG map uses API topology and ordered edge IDs. Base roads have casings, hierarchy, block geometry, river, labels, nodes, route overlays, marker cards, zoom controls, fit-to-view, layer tabs, route toggles, and selected-vehicle details.
- No CSS/emoji placeholder assets. Use Lucide for controls and functional SVG primitives for topology.
- At 686px, collapse to one column without horizontal overflow; keep 44px tap targets, keyboard selection, focus indicators, and reduced-motion behavior.

**TDD steps:**

1. Add failing client and component tests for API snapshot mapping, four stages, auto countdown, route-edge geometry, tabs, toggles, selection, and responsive/accessibility contract.
2. Run the targeted Vitest files and confirm red.
3. Implement types/client/hook and component markup with realistic loading, error, empty, and live states.
4. Implement scoped V8 CSS and import it after existing styles.
5. Re-run targeted frontend tests, lint, and build.
6. Inspect diff and commit: `feat: build V8 vehicle operations map command center`.

## Task 8: Demo data, end-to-end verification, and design QA

**Files:**

- Modify: `backend/app/sandtable/seed_data.py`
- Modify: `backend/app/seed.py`
- Create: `backend/tests/unit/test_vehicle_operations_seed.py`
- Create: `design-qa.md`

**TDD and verification steps:**

1. Add a failing seed test that ensures one deterministic V8 breakdown case is created idempotently.
2. Implement rescue unit, bay, mission, maintenance order, status history, and outbox seed data without resetting live state on every restart.
3. Rebuild/restart Docker services and apply migration/seed.
4. Verify the full user journey: employee report, task accepted, worker decision, replacement dispatch, rescue/tow, maintenance countdown, automatic QA, and vehicle return to `AVAILABLE`.
5. Capture the implementation at 1440x900 and 686px.
6. Put the V8 reference and implementation screenshots into the same comparison input; fix layout, typography, color, spacing, crop, route, and interaction mismatches.
7. Record QA evidence and `final result: passed` in root `design-qa.md`. If an environment limitation prevents a required check, record `final result: blocked` and the exact blocker instead.
8. Run required verification:

```powershell
python -m ruff check backend
python -m pytest
npm run lint --prefix frontend
npm run test --prefix frontend
npm run build --prefix frontend
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常/.worktrees/vehicle-rescue-maintenance-v8' diff --check
```

9. Inspect final `git diff`, commit the QA/seed adjustments, and leave the verified local preview running.

## Completion evidence

- The failed-then-passed commands for every behavior slice.
- Final backend, frontend, and Docker integration command output.
- Screenshot comparison at identical 1440x900 viewport plus compact-width screenshot.
- `design-qa.md` with the final rubric result.
- Git commit hashes for each phase and a clean tracked worktree (existing unrelated files outside this worktree remain untouched).
