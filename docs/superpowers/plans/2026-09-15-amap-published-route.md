# AMap Published Route Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make road-block anomaly dispatches automatically produce an auditable route and show the published route on real AMap roads to the assigned driver.

**Architecture:** Preserve structured anomaly context through the existing asynchronous pipeline, keep local Dijkstra as the safety authority, and enrich its selected node sequence through a narrow real-road routing service. Persist the real-road result inside existing route evidence and render it only for a published employee task, with AMap JS road matching and the current SVG route as fallback.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy, Redis Streams, LangGraph, httpx, React 19, TypeScript, Vite, Vitest, AMap Web Service V5 and JS API 2.0.

**Spec:** `docs/superpowers/specs/2026-09-15-amap-published-route-design.md`

## Global Constraints

- Keep the production path asynchronous: frontend → FastAPI → Redis Streams → Worker → LangGraph → MySQL/Qdrant/providers → WebSocket/status → frontend.
- Agents consume narrow application interfaces and do not import Redis, SQLAlchemy, Qdrant, or vendor SDKs.
- Use behavior-level TDD and never weaken an existing test.
- Read keys only from environment variables and never log or return secrets.
- Provider failures use an explicit async timeout and a bounded fallback under one second.
- MySQL remains the source of truth; route geometry is stored in existing dispatch evidence.
- Preserve Decimal values as strings at the API boundary.
- Employee users do not receive `runtime:read` solely to remove a UI error.

---

### Task 1: Preserve anomaly location and restore demo planning context

**Files:**
- Modify: `backend/tests/anomaly_reports/test_anomaly_report_service.py`
- Modify: `backend/tests/workers/test_dispatch_worker.py`
- Modify: `backend/tests/sandtable/test_sqlalchemy_repository.py`
- Modify: `backend/app/api/v1/schemas.py`
- Modify: `backend/app/anomaly_reports/service.py`
- Modify: `backend/app/services/dispatch_task_api_service.py`
- Modify: `backend/app/streams/models.py`
- Modify: `backend/app/workers/dispatch_worker.py`
- Modify: `backend/app/sandtable/sqlalchemy_repository.py`

**Interfaces:**
- Consumes: `AnomalyReportCommand.incident_node_id`, `AnomalyReportCommand.affected_edge_id`, `Order.origin`, and `Order.destination`.
- Produces: optional `CreateDispatchTaskRequest.incident_node_id`, optional `CreateDispatchTaskRequest.affected_edge_id`, matching optional Redis payload keys, and graph input `affected_edge_ids: list[str]`.

- [ ] **Step 1: Write failing anomaly propagation tests**

Extend the structured road-location test to assert:

```python
message = queue.messages[0]
assert message.payload["incident_node_id"] is None
assert message.payload["affected_edge_id"] == "E04"
```

- [ ] **Step 2: Run the propagation tests and confirm failure**

Run: `pytest backend/tests/anomaly_reports/test_anomaly_report_service.py::test_submit_persists_structured_road_location backend/tests/workers/test_dispatch_worker.py::test_task_message_to_graph_input_preserves_reported_vehicle_status -q`

Expected: FAIL because the current payload omits structured road location.

- [ ] **Step 3: Extend the API, Redis, submission, and graph-input contracts**

Add optional `incident_node_id` and `affected_edge_id` fields, publish them from `DispatchTaskApiService`, retain backward-compatible parsing in `DispatchTaskMessage._payload`, and convert the singular edge to `affected_edge_ids` in `task_message_to_graph_input`.

- [ ] **Step 4: Write and run a failing name-fallback repository test**

Create an order with null station IDs but `origin="新平县中心仓"` and `destination="北岭村驿站"`; assert `SqlAlchemySandtableRepository.load()` returns `origin_node_id="N01"` and `destination_node_id="N11"`.

Run: `pytest backend/tests/sandtable/test_sqlalchemy_repository.py -q`

Expected: FAIL because the repository currently searches only by station ID.

- [ ] **Step 5: Implement unique node-name fallback and verify Task 1**

Resolve a missing station first by `RoadNode.name`; accept exactly one match and otherwise raise the existing incomplete-context `LookupError`. Run:

`pytest backend/tests/anomaly_reports/test_anomaly_report_service.py backend/tests/workers/test_dispatch_worker.py backend/tests/sandtable/test_sqlalchemy_repository.py -q`

Expected: PASS.

- [ ] **Step 6: Inspect and commit Task 1**

Run `git diff -- backend/app backend/tests`, then commit with `fix: preserve road anomaly routing context`.

### Task 2: Add the narrow AMap real-road provider and bounded fallback

**Files:**
- Create: `backend/app/real_routes/__init__.py`
- Create: `backend/app/real_routes/models.py`
- Create: `backend/app/real_routes/protocols.py`
- Create: `backend/app/real_routes/demo_coordinates.py`
- Create: `backend/app/real_routes/amap_provider.py`
- Create: `backend/app/real_routes/service.py`
- Create: `backend/tests/real_routes/test_amap_provider.py`
- Create: `backend/tests/real_routes/test_service.py`
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `backend/tests/unit/test_docker_runtime_files.py`

**Interfaces:**
- Produces: `GeoPoint(node_id: str | None, longitude: Decimal, latitude: Decimal)`, `RealRoadRoute(provider: str, source: str, status: str, coordinate_system: str, mapping_version: str, distance_meters: int | None, duration_seconds: int | None, waypoints: tuple[GeoPoint, ...], polyline: tuple[GeoPoint, ...], fallback_reason: str | None)`, `DrivingRouteProvider.plan(origin, destination, waypoints)`, and `RealRoadRouteService.plan(node_ids)`.

- [ ] **Step 1: Write failing coordinate and provider parsing tests**

Assert `N01` maps to `103.044800,25.226500`; feed an injected `httpx.MockTransport` a V5 response containing two paths and assert the provider selects the lowest-duration valid path, parses step polylines in order, and never exposes the request key.

- [ ] **Step 2: Run the provider tests and confirm import failure**

Run: `pytest backend/tests/real_routes/test_amap_provider.py -q`

Expected: FAIL because `app.real_routes` does not exist.

- [ ] **Step 3: Implement immutable models, coordinate mapping, protocol, and HTTP provider**

Call `GET /v5/direction/driving` with GCJ-02 coordinates, `alternative_route=2`, explicit `httpx.Timeout`, and key only in request params. Normalize timeout, HTTP, response-status, and malformed-payload failures to existing `ProviderTimeout` or `ProviderUnavailable` exceptions without including the URL or key.

- [ ] **Step 4: Write failing service fallback tests**

Assert that missing provider configuration and provider failure both return `source="CLIENT_WAYPOINT_FALLBACK"`, `status="CLIENT_MATCH_REQUIRED"`, the complete mapped waypoint sequence, and a safe fixed reason.

- [ ] **Step 5: Implement the service and configuration wiring**

Add secret `amap_web_service_key`, URL, 0.8-second timeout, and circuit-breaker settings. Add only variable names/defaults to `.env.example` and Docker backend/worker environment. The service must return immediately with client fallback when no key is configured.

- [ ] **Step 6: Run and commit Task 2**

Run: `pytest backend/tests/real_routes backend/tests/unit/test_docker_runtime_files.py -q`

Expected: PASS. Inspect `git diff`, then commit with `feat: add bounded AMap real-road provider`.

### Task 3: Persist and expose the selected real-road route

**Files:**
- Modify: `backend/app/graph/dependencies.py`
- Modify: `backend/app/graph/builder.py`
- Modify: `backend/app/graph/state.py`
- Modify: `backend/app/runtime.py`
- Modify: `backend/app/agents/routing.py`
- Modify: `backend/app/agents/dispatch.py`
- Modify: `backend/app/events/graph_payloads.py`
- Modify: `backend/app/api/v1/schemas.py`
- Modify: `backend/app/services/dispatch_task_api_service.py`
- Modify: `backend/tests/graph/test_routing_agent.py`
- Modify: `backend/tests/api/test_dispatch_tasks.py`

**Interfaces:**
- Consumes: `RealRoadRouteService.plan(node_ids: Sequence[str]) -> RealRoadRoute`.
- Produces: graph-state and route-evidence key `real_road_route`, plus nullable API field `RoutePlanResponse.real_road_route`.

- [ ] **Step 1: Write a failing routing-agent enrichment test**

Inject a capturing real-road service, run a blocked-edge plan, and assert it receives the exact `recommended_path.node_ids`; assert the node patch includes the serialized result and retains `DIJKSTRA_V1` as the safety algorithm.

- [ ] **Step 2: Run the routing-agent test and confirm failure**

Run: `pytest backend/tests/graph/test_routing_agent.py -q`

Expected: FAIL because the graph has no real-road dependency or state.

- [ ] **Step 3: Wire and persist the enrichment**

Add the dependency to `GraphDependencies`, invoke it only after a reachable recommended path exists, serialize Decimals with `format(value, "f")`, project safe event fields, and include `real_road_route` in the existing `ROUTE_CALCULATION` evidence payload.

- [ ] **Step 4: Write a failing result reconstruction test**

Seed route evidence with a verified real-road result and assert `GET /api/v1/dispatch-tasks/{task_id}/result` returns the exact coordinate strings, source, status, distance, and duration.

- [ ] **Step 5: Implement strict response models and reconstruction**

Add strict `GeoPointResponse` and `RealRoadRouteResponse`, validate evidence through Pydantic, and keep malformed evidence behavior explicit by returning no route evidence rather than fabricating coordinates.

- [ ] **Step 6: Run and commit Task 3**

Run: `pytest backend/tests/graph/test_routing_agent.py backend/tests/api/test_dispatch_tasks.py -q`

Expected: PASS. Inspect `git diff`, then commit with `feat: persist published real-road route evidence`.

### Task 4: Render the published route on AMap for the assigned driver

**Files:**
- Create: `frontend/src/components/published-amap-route-map.tsx`
- Create: `frontend/tests/published-amap-route-map.test.tsx`
- Modify: `frontend/src/services/api/dispatch-adapter.ts`
- Modify: `frontend/src/pages/api-dispatch-detail-page.tsx`
- Modify: `frontend/src/styles/index.css`
- Modify: `frontend/tests/api-dispatch-adapter.test.ts`
- Modify: `frontend/tests/dispatch-v2-evidence.test.tsx`

**Interfaces:**
- Consumes: `RoutePlanResponse.real_road_route`, `RoutePlanResponse.recommended_path`, `PublicationResultResponse.status`, and frontend AMap runtime configuration.
- Produces: `PublishedAmapRouteMap` with `READY`, `MATCHING`, and `FALLBACK` display states.

- [ ] **Step 1: Write failing component tests**

Mock the AMap loader. Assert a verified backend polyline creates an `AMap.Polyline`; assert `CLIENT_MATCH_REQUIRED` calls `AMap.Driving.search` with the persisted origin, destination, and intermediate waypoints; assert missing AMap configuration renders the local fallback and keeps route instructions visible.

- [ ] **Step 2: Run the component tests and confirm failure**

Run: `npm test -- --run frontend/tests/published-amap-route-map.test.tsx`

Expected: FAIL because the component and types do not exist.

- [ ] **Step 3: Implement API types and the focused map component**

Load AMap JS API 2.0 only when mounted, configure the existing security code before loading, draw start/end markers and a blue route, fit the view once, and clean up map/provider objects on unmount. Never make the component choose a different business route; it may only road-match persisted waypoints.

- [ ] **Step 4: Write failing employee detail-page tests**

Render an employee with `dispatch:read` and a published result. Assert the page contains “已发布真实道路路线”, mounts the map, and does not contain the RuntimeWorkbench permission error. Render an unpublished result and assert the map is absent.

- [ ] **Step 5: Integrate the employee-only published view and styles**

Show the map only when `!canPublish`, publication is `PUBLISHED`, and route evidence exists. Do not mount `RuntimeWorkbench` for employees. Keep supervisor live-map and evidence panels unchanged.

- [ ] **Step 6: Run and commit Task 4**

Run: `npm test -- --run frontend/tests/published-amap-route-map.test.tsx frontend/tests/api-dispatch-adapter.test.ts frontend/tests/dispatch-v2-evidence.test.tsx`

Expected: PASS. Run `npm run lint`, inspect `git diff`, then commit with `feat: show published AMap route to drivers`.

### Task 5: Prove the road-block report completes and publishes

**Files:**
- Modify: `backend/tests/api/test_anomaly_reports.py`
- Modify: `backend/tests/api/test_dispatch_api_e2e.py`
- Modify: `docs/final/FINAL_FACTS.md`
- Create: `docs/verification/amap-published-route-results.md`

**Interfaces:**
- Consumes: the complete anomaly-report, Redis, Worker, audit, publication, result API, and employee UI contracts from Tasks 1-4.
- Produces: a regression test for the screenshot failure and an evidence-backed verification record.

- [ ] **Step 1: Write the end-to-end failing regression**

Submit a `ROAD_BLOCKED` report with `affected_edge_id="E04"` against an employee-owned demo order, run the Worker, and assert: no recommended edge is `E04`, terminal status is `APPROVED`, automatic publication is `PUBLISHED`, result includes a non-empty `recommended_path`, and the message is acknowledged rather than moved to DLQ.

- [ ] **Step 2: Run the targeted end-to-end test**

Run: `pytest backend/tests/api/test_dispatch_api_e2e.py -q`

Expected: PASS after Tasks 1-4; any failure must be diagnosed before broad verification.

- [ ] **Step 3: Run required verification**

Run:

```text
ruff check backend
pytest
npm run lint
npm test -- --run
npm run build
docker compose --env-file .docker.env run --rm migration
git -c safe.directory=C:/Users/24090/OneDrive/Desktop/县域物流识别异常 diff --check
```

Record only actual command output and do not claim a Docker dependency test that was not run.

- [ ] **Step 4: Update final facts and verification record**

Replace the obsolete statement that routing never uses AMap with the precise hybrid behavior and fallback boundary. Record commands, exit codes, the tested task scenario, and any provider configuration limitation in `docs/verification/amap-published-route-results.md`.

- [ ] **Step 5: Inspect and commit the final slice**

Review `git diff --stat`, `git diff --check`, and `git status --short`; commit with `test: verify published AMap rerouting flow`.

