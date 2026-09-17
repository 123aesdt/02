# Complete Fleet Candidate Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Populate every dispatch candidate row with truthful, deterministic vehicle, driver, pickup, and scoring evidence.

**Architecture:** Extend fleet evaluation so hard-excluded but reachable vehicles still receive comparison route and score evidence, while eligibility stays false. Persist the full candidate shape for every vehicle and render explicit non-applicable states in the existing React table.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Pytest, React, TypeScript, Vitest, Docker Compose

**Spec:** `docs/superpowers/specs/2026-09-17-complete-fleet-candidate-evidence-design.md`

## Global Constraints

- Use TDD: add a behavior-level failing test, run it, implement the smallest behavior, and rerun it.
- MySQL remains the source of truth; evidence must be persisted rather than generated randomly by the frontend.
- Preserve the existing hard eligibility constraints and selected-vehicle reservation behavior.
- Do not expose or log secrets.
- Inspect `git diff` after each implementation phase.
- Before completion run backend lint/tests, frontend lint/test/build, targeted Docker integration, and `git -c safe.directory=<workspace> diff --check`.

---

### Task 1: Complete fleet evaluation evidence

**Files:**
- Modify: `backend/tests/fleet/test_allocation_service.py`
- Modify: `backend/app/fleet/service.py`

**Interfaces:**
- Consumes: `FleetVehicleSnapshot`, `FleetAllocationRequest`, and `TravelTimeEstimator`.
- Produces: `FleetAllocationService.allocate(...) -> FleetAllocationResult` with pickup and score evidence on every reachable candidate.

- [x] **Step 1: Write the failing service test**

Add a test in which a vehicle fails `DRIVER_UNAVAILABLE` or `CARGO_CAPABILITY_MISMATCH` but has a reachable pickup path. Assert `eligible is False`, exclusion reasons remain intact, and `pickup_distance_km`, `pickup_eta_minutes`, `score`, and all `score_components` are populated.

- [x] **Step 2: Run the test and verify the current short-circuit fails**

Run: `pytest backend/tests/fleet/test_allocation_service.py -q`

Expected: the new assertions fail because `_evaluate` currently returns `_rejected` before route estimation.

- [x] **Step 3: Implement comparison evidence without weakening eligibility**

Refactor `_evaluate` to collect hard reasons, attempt pickup estimation, append reachability and weight reasons when applicable, compute score components whenever pickup exists, and construct one `VehicleCandidate` whose `eligible` value is `not reasons`. Preserve delivery reachability checks and existing selected-candidate sorting.

- [x] **Step 4: Run fleet tests and inspect the diff**

Run: `pytest backend/tests/fleet/test_allocation_service.py -q`

Run: `git diff -- backend/app/fleet/service.py backend/tests/fleet/test_allocation_service.py`

Expected: all fleet tests pass and the diff contains no eligibility-rule relaxation.

### Task 2: Persist every complete candidate snapshot

**Files:**
- Modify: `backend/tests/unit/test_dispatch_service.py`
- Modify: `backend/tests/api/test_dispatch_tasks.py`
- Modify: `backend/app/dispatch/service.py`

**Interfaces:**
- Consumes: `candidate_vehicles: Sequence[Mapping[str, object]]` from the graph.
- Produces: `FLEET_ALLOCATION.payload_json["candidates"]` where each entry has the full `_compact_vehicle_candidate` shape.

- [x] **Step 1: Write failing persistence and API tests**

Extend dispatch persistence fixtures with a non-selected rejected candidate containing driver, status, load, vehicle evidence, pickup, score, and score components. Assert the stored evidence and task-detail response preserve every field.

- [x] **Step 2: Run targeted tests and verify evidence is truncated**

Run: `pytest backend/tests/unit/test_dispatch_service.py backend/tests/api/test_dispatch_tasks.py -q`

Expected: assertions fail because non-selected candidates currently retain only `vehicle_id`, `score`, and `exclusion_reasons`.

- [x] **Step 3: Persist the full bounded shape for all candidates**

Change `_compact_fleet_evidence` to call `_compact_vehicle_candidate` for every candidate. Keep the existing allow-listed fields and selected-candidate identity checks.

- [x] **Step 4: Run targeted tests and inspect the diff**

Run: `pytest backend/tests/unit/test_dispatch_service.py backend/tests/api/test_dispatch_tasks.py -q`

Run: `git diff -- backend/app/dispatch/service.py backend/tests/unit/test_dispatch_service.py backend/tests/api/test_dispatch_tasks.py`

Expected: targeted tests pass and evidence remains allow-listed and deterministic.

### Task 3: Render explicit complete table states

**Files:**
- Modify: `frontend/tests/fleet-allocation-panel.test.tsx`
- Modify: `frontend/src/components/fleet-allocation-panel.tsx`

**Interfaces:**
- Consumes: `VehicleAllocationResponse.candidate_vehicles` from the task API.
- Produces: semantic table rows that distinguish complete values, unassigned drivers, unreachable pickup, not scored, and excluded-from-ranking states.

- [x] **Step 1: Write failing component expectations**

Update fixtures so a rejected reachable candidate contains complete comparison evidence and add an unreachable candidate. Assert the reachable row shows all values, the unreachable row says `无法到达` and `不计分`, and rejected rows say `不参与排名` instead of an em dash.

- [x] **Step 2: Run the component test and verify current placeholders fail**

Run: `npm test -- --run tests/fleet-allocation-panel.test.tsx` from `frontend`.

Expected: current `未提供` and `—` text fails the new assertions.

- [x] **Step 3: Implement explicit evidence labels**

Add small pure display helpers keyed by candidate eligibility and exclusion reasons. Keep ranking computation derived during render and avoid new state or effects.

- [x] **Step 4: Run frontend tests and inspect the diff**

Run: `npm test -- --run tests/fleet-allocation-panel.test.tsx` from `frontend`.

Run: `git diff -- frontend/src/components/fleet-allocation-panel.tsx frontend/tests/fleet-allocation-panel.test.tsx`

Expected: component tests pass and no random/mock-only production data is introduced.

### Task 4: Full verification and Docker demonstration

**Files:**
- Verify only: backend, frontend, and Docker runtime.

**Interfaces:**
- Consumes: the completed backend evidence pipeline and frontend renderer.
- Produces: a repeatable demo task whose detail response and visible table contain complete candidate data.

- [x] **Step 1: Run repository verification**

Run: `ruff check backend`

Run: `pytest`

Run from `frontend`: `npm run lint`, `npm test -- --run`, and `npm run build`.

- [x] **Step 2: Rebuild and restart Docker services**

Run the repository's existing Docker Compose build/start command for backend, worker, and frontend, preserving database volumes.

- [x] **Step 3: Reset and execute a real demo task**

Use the existing demo reset endpoint, submit the vehicle-breakdown scenario, wait for terminal success, and query task detail. Assert 20 candidate rows are returned and every reachable candidate has driver/vehicle evidence, pickup metrics, score, and score components.

- [x] **Step 4: Repeat the same demonstration**

Reset again, submit the same scenario, and verify the second task also completes with the same deterministic candidate evidence.

- [x] **Step 5: Run final diff checks**

Run: `git -c safe.directory=C:/Users/24090/OneDrive/Desktop/县域物流识别异常 diff --check`

Run: `git status --short`

Expected: diff check is clean and status lists only intentional source, test, and documentation changes.
