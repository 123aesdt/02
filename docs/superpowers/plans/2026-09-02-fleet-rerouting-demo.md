# CountyFlow Offline Fleet Rerouting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fully offline virtual-county demo in which a broken vehicle triggers a calculated replacement-vehicle assignment and a blocked road triggers a calculated Dijkstra reroute, with durable evidence visible in the API, WebSocket stream, and frontend.

**Architecture:** Seed one coherent “新平县数字沙盘” into MySQL, load its order/fleet/road context through narrow application interfaces, extend the existing capacity and routing agents with deterministic fleet scoring and Dijkstra pathfinding, and atomically persist the selected vehicle, driver, route, and evidence. Keep the existing eight-agent order and the Redis Streams worker lifecycle; the frontend renders only backend-sourced evidence and draws the road graph from returned node coordinates.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, MySQL, Redis Streams, LangGraph, Pydantic, React, TypeScript, SVG, Vitest, Playwright, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-02-fleet-rerouting-demo-design.md`

## Global Constraints

- Keep the production path asynchronous: frontend → FastAPI → Redis Streams → Worker → LangGraph → MySQL/Qdrant/Neo4j → WebSocket/status query → frontend.
- Agents consume narrow application interfaces and must not import Redis, SQLAlchemy, Qdrant, Neo4j, or vendor SDKs directly.
- MySQL is the source of truth for orders, fleet resources, road state, dispatches, and audit evidence.
- Use `Decimal` for distance, weight, load, score, and cost values.
- Use SQLAlchemy `version_id_col` for mutable fleet/dispatch concurrency and convert `StaleDataError` to a domain conflict.
- Preserve stable `task_id` and `idempotency_key`; acknowledge Redis messages only after durable terminal persistence.
- Do not call external map APIs and do not let the frontend synthesize vehicle or route decisions.
- Test doubles are confined to tests. The Docker development runtime reads virtual business data from MySQL.
- Use TDD for every task: failing behavior test, observed failure, minimal real implementation, passing test.
- Preserve existing user changes in the dirty worktree. Inspect only task-scoped diffs after every task.
- Do not report Docker, browser, or service verification as passed unless the corresponding command actually completed successfully.

---

## File Structure

### New backend files

- `backend/app/models/station.py`: SQLAlchemy station entity.
- `backend/app/models/fleet_driver.py`: SQLAlchemy driver entity with optimistic versioning.
- `backend/app/models/fleet_vehicle.py`: SQLAlchemy vehicle entity with optimistic versioning.
- `backend/app/models/road.py`: SQLAlchemy road-node and road-edge entities.
- `backend/app/models/dispatch_evidence.py`: durable fleet and route evidence entity.
- `backend/app/sandtable/models.py`: immutable order/anomaly context DTOs.
- `backend/app/sandtable/protocols.py`: context-provider interface.
- `backend/app/sandtable/sqlalchemy_repository.py`: MySQL context loading and idempotent road-status mutation.
- `backend/app/sandtable/service.py`: deterministic anomaly-to-node/edge resolution.
- `backend/app/sandtable/seed_data.py`: exact Section 7 spec records.
- `backend/app/road_network/models.py`: immutable graph, request, path, and route-candidate DTOs.
- `backend/app/road_network/protocols.py`: road-network provider and pathfinder interfaces.
- `backend/app/road_network/sqlalchemy_repository.py`: MySQL road snapshot reader.
- `backend/app/road_network/dijkstra.py`: pure deterministic pathfinding.
- `backend/app/fleet/models.py`: allocation request/candidate/result DTOs.
- `backend/app/fleet/protocols.py`: fleet provider and travel estimator interfaces.
- `backend/app/fleet/sqlalchemy_repository.py`: MySQL fleet snapshot reader.
- `backend/app/fleet/service.py`: hard filters and `FLEET_SCORE_V1`.
- `backend/alembic/versions/20260902_13_offline_fleet_routing.py`: schema migration.
- Focused tests under `backend/tests/migrations`, `backend/tests/sandtable`, `backend/tests/road_network`, `backend/tests/fleet`, and `backend/tests/concurrency`.

### Modified backend files

- ORM registration: `backend/app/models/__init__.py`.
- Existing entities: `backend/app/models/order.py`, `backend/app/models/anomaly.py`, `backend/app/models/dispatch.py`.
- Seeds/runtime: `backend/app/seed.py`, `backend/app/runtime.py`.
- Graph boundary: `backend/app/graph/state.py`, `backend/app/graph/dependencies.py`, `backend/app/graph/builder.py`.
- Agents/services: `backend/app/agents/intake.py`, `backend/app/agents/capacity.py`, `backend/app/agents/routing.py`, `backend/app/agents/dispatch.py`, `backend/app/agents/audit.py`, `backend/app/capacity/models.py`, `backend/app/routing/models.py`, `backend/app/routing/service.py`, `backend/app/dispatch/service.py`, `backend/app/audit/service.py`.
- Evidence/API/publication: `backend/app/events/graph_adapter.py`, `backend/app/api/v1/schemas.py`, `backend/app/services/dispatch_task_api_service.py`, `backend/app/publications/service.py`.

### Frontend files

- New `frontend/src/components/fleet-allocation-panel.tsx`.
- Replace static behavior in `frontend/src/components/route-visual.tsx` with a typed dynamic SVG.
- Extend `frontend/src/components/capacity-evidence-panel.tsx`, `frontend/src/components/routing-evidence-panel.tsx`, `frontend/src/pages/api-dispatch-detail-page.tsx`, `frontend/src/types/dispatch.ts`, `frontend/src/services/api/dispatch-adapter.ts`, and presentation styles/labels.
- Add or extend focused Vitest and Playwright tests.

---

### Task 1: Persist the Virtual Fleet and Road Schema

**Files:**
- Create: `backend/app/models/station.py`
- Create: `backend/app/models/fleet_driver.py`
- Create: `backend/app/models/fleet_vehicle.py`
- Create: `backend/app/models/road.py`
- Create: `backend/app/models/dispatch_evidence.py`
- Create: `backend/alembic/versions/20260902_13_offline_fleet_routing.py`
- Create: `backend/tests/migrations/test_offline_fleet_routing_migration.py`
- Modify: `backend/app/models/order.py`
- Modify: `backend/app/models/anomaly.py`
- Modify: `backend/app/models/dispatch.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/tests/unit/test_models.py`

**Interfaces:**
- Produces ORM types `LogisticsStation`, `FleetDriver`, `FleetVehicle`, `RoadNode`, `RoadEdge`, and `DispatchEvidence`.
- Extends `Order` with `cargo_weight_kg`, `cargo_type`, `origin_station_id`, and `destination_station_id`.
- Extends `Anomaly` with `incident_node_id` and `affected_edge_id`.
- Extends `Dispatch` with `original_vehicle_id`, `target_vehicle_id`, and `transfer_node_id`.

- [ ] **Step 1: Write the failing migration/model test**

```python
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from app.models.dispatch import Dispatch
from app.models.fleet_vehicle import FleetVehicle
from app.models.order import Order
from app.models.road import RoadEdge


def test_offline_fleet_models_expose_required_fields() -> None:
    assert {"cargo_weight_kg", "cargo_type", "origin_station_id", "destination_station_id"} <= set(Order.__table__.columns)
    assert {"original_vehicle_id", "target_vehicle_id", "transfer_node_id"} <= set(Dispatch.__table__.columns)
    assert FleetVehicle.__mapper__.version_id_col is FleetVehicle.__table__.c.version
    assert RoadEdge.__mapper__.version_id_col is RoadEdge.__table__.c.version


def test_offline_fleet_migration_continues_from_current_head() -> None:
    path = Path(__file__).parents[2] / "alembic" / "versions" / "20260902_13_offline_fleet_routing.py"
    spec = spec_from_file_location("offline_fleet_routing", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "20260902_13"
    assert module.down_revision == "20260901_12"
```

- [ ] **Step 2: Run the focused test and confirm failure**

Run from repository root:

```powershell
& .\.venv\Scripts\python.exe -m pytest backend/tests/migrations/test_offline_fleet_routing_migration.py -q
```

Expected: FAIL because the new ORM modules and migration do not exist.

- [ ] **Step 3: Add focused ORM entities**

Use `Numeric(..., asdecimal=True)` for decimal fields and exact status strings from the spec. The vehicle pattern must include real SQLAlchemy versioning:

```python
class FleetVehicle(TimestampMixin, Base):
    __tablename__ = "fleet_vehicles"
    __table_args__ = (
        UniqueConstraint("vehicle_id", name="uq_fleet_vehicles_vehicle_id"),
        UniqueConstraint("plate_no", name="uq_fleet_vehicles_plate_no"),
        Index("ix_fleet_vehicles_status_node", "status", "current_node_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(String(64), nullable=False)
    plate_no: Mapped[str] = mapped_column(String(32), nullable=False)
    vehicle_type: Mapped[str] = mapped_column(String(32), nullable=False)
    max_load_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    current_load_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    cargo_capability: Mapped[str] = mapped_column(String(32), nullable=False)
    gross_weight_tons: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    assigned_driver_id: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
```

Define `RoadNode` and `RoadEdge` in one road-focused module; define the other entities in their named files. Add all new models to `app.models.__all__` so metadata creation and migrations see them.

- [ ] **Step 4: Write the Alembic upgrade and downgrade**

Create all six tables and their named indexes/unique constraints, then batch-add the order, anomaly, and dispatch columns. `dispatch_evidence.dispatch_id` must use `ondelete="CASCADE"`; operational foreign keys use `RESTRICT`. Downgrade in reverse dependency order and remove only columns created by this revision.

- [ ] **Step 5: Run model and migration tests**

```powershell
& .\.venv\Scripts\python.exe -m pytest backend/tests/migrations/test_offline_fleet_routing_migration.py backend/tests/unit/test_models.py -q
```

Expected: PASS.

- [ ] **Step 6: Inspect and commit the scoped change**

```powershell
git diff -- backend/app/models backend/alembic/versions/20260902_13_offline_fleet_routing.py backend/tests/migrations/test_offline_fleet_routing_migration.py backend/tests/unit/test_models.py
git diff --check -- backend/app/models backend/alembic/versions/20260902_13_offline_fleet_routing.py
git add backend/app/models/station.py backend/app/models/fleet_driver.py backend/app/models/fleet_vehicle.py backend/app/models/road.py backend/app/models/dispatch_evidence.py backend/app/models/order.py backend/app/models/anomaly.py backend/app/models/dispatch.py backend/app/models/__init__.py backend/alembic/versions/20260902_13_offline_fleet_routing.py backend/tests/migrations/test_offline_fleet_routing_migration.py backend/tests/unit/test_models.py
git commit -m "feat: add offline fleet and road schema"
```

---

### Task 2: Seed and Resolve the Complete New County Sandtable

**Files:**
- Create: `backend/app/sandtable/__init__.py`
- Create: `backend/app/sandtable/models.py`
- Create: `backend/app/sandtable/protocols.py`
- Create: `backend/app/sandtable/seed_data.py`
- Create: `backend/app/sandtable/sqlalchemy_repository.py`
- Create: `backend/app/sandtable/service.py`
- Create: `backend/tests/sandtable/test_seed_data.py`
- Create: `backend/tests/sandtable/test_sqlalchemy_repository.py`
- Modify: `backend/app/seed.py`
- Modify: `backend/tests/unit/test_seed.py`

**Interfaces:**
- Produces `SandtableTaskContext(order_id: int, order_no: str, cargo_weight_kg: Decimal, cargo_type: str, origin_node_id: str, destination_node_id: str, current_vehicle_id: str, current_driver_id: str, incident_node_id: str | None, affected_edge_ids: tuple[str, ...], road_network_version: int)`.
- Produces protocol `SandtableContextProvider.load(order_id: int) -> SandtableTaskContext` and `set_edge_status(edge_id: str, status: str) -> int`.
- Produces `SandtableContextService.resolve(order_id, anomaly_type, description, vehicle_id) -> SandtableTaskContext`.

- [ ] **Step 1: Write failing seed-contract tests**

```python
from app.sandtable.seed_data import DRIVERS, ORDERS, ROAD_EDGES, ROAD_NODES, STATIONS, VEHICLES


def test_new_county_seed_has_the_approved_inventory() -> None:
    assert (len(STATIONS), len(ROAD_NODES), len(ROAD_EDGES)) == (8, 18, 26)
    assert (len(DRIVERS), len(VEHICLES), len(ORDERS)) == (10, 12, 12)
    edge = next(item for item in ROAD_EDGES if item["edge_id"] == "E04")
    vehicle = next(item for item in VEHICLES if item["vehicle_id"] == "V-005")
    assert (edge["from_node_id"], edge["to_node_id"], edge["distance_km"], edge["base_minutes"]) == ("N04", "N05", "2.50", 5)
    assert (vehicle["cargo_capability"], vehicle["max_load_kg"], vehicle["current_load_kg"]) == ("COLD_CHAIN", "1000.00", "100.00")
```

Add a repository test that creates metadata in SQLite, seeds twice, and asserts counts remain unchanged and `DEMO-ORDER-001` resolves to N01→N06 with 700 kg cold-chain cargo.

- [ ] **Step 2: Run and observe failure**

```powershell
& .\.venv\Scripts\python.exe -m pytest backend/tests/sandtable backend/tests/unit/test_seed.py -q
```

Expected: FAIL because the sandtable package and records do not exist.

- [ ] **Step 3: Encode the approved data exactly once**

In `seed_data.py`, define immutable tuples of `MappingProxyType` rows. Copy every station, node, edge, driver, vehicle, and order row from Spec Section 7 exactly. Store decimal literals as strings in constants and convert with `Decimal` only when constructing ORM entities. Export these names:

```python
__all__ = ["STATIONS", "ROAD_NODES", "ROAD_EDGES", "DRIVERS", "VEHICLES", "ORDERS"]
```

- [ ] **Step 4: Implement idempotent seed and context repository**

Use unique business IDs for upserts. Do not delete user-created rows. `set_edge_status` must be idempotent: return the current version without incrementing if status is already equal; otherwise update status and commit the version increment.

```python
class SandtableContextProvider(Protocol):
    def load(self, order_id: int) -> SandtableTaskContext: ...
    def set_edge_status(self, edge_id: str, status: str) -> int: ...
```

`SandtableContextService.resolve` uses exact aliases: plate `新物冷链-01`→V-001, `新平路 K3.2`→N04, and `新平路东河桥段`→E04. For `ROAD_BLOCKED`, mark E04 blocked before returning. If no unique edge alias is found, raise `RoadLocationUnresolved` and never guess.

- [ ] **Step 5: Wire seeding without replacing existing demo accounts**

Call `seed_new_county_sandtable(session)` inside the existing development-only `seed_database`. Keep all existing employee/account data and unrelated demo records intact. Update existing seed tests to assert new rows rather than exact totals across old and new datasets.

- [ ] **Step 6: Run focused tests and inspect diff**

```powershell
& .\.venv\Scripts\python.exe -m pytest backend/tests/sandtable backend/tests/unit/test_seed.py -q
git diff -- backend/app/sandtable backend/app/seed.py backend/tests/sandtable backend/tests/unit/test_seed.py
git diff --check -- backend/app/sandtable backend/app/seed.py
```

Expected: PASS; repeated seeding leaves 8/18/26/10/12/12 approved records.

- [ ] **Step 7: Commit**

```powershell
git add backend/app/sandtable/__init__.py backend/app/sandtable/models.py backend/app/sandtable/protocols.py backend/app/sandtable/seed_data.py backend/app/sandtable/sqlalchemy_repository.py backend/app/sandtable/service.py backend/app/seed.py backend/tests/sandtable/test_seed_data.py backend/tests/sandtable/test_sqlalchemy_repository.py backend/tests/unit/test_seed.py
git commit -m "feat: seed new county logistics sandtable"
```

---

### Task 3: Implement Deterministic Dijkstra Pathfinding

**Files:**
- Create: `backend/app/road_network/__init__.py`
- Create: `backend/app/road_network/models.py`
- Create: `backend/app/road_network/protocols.py`
- Create: `backend/app/road_network/dijkstra.py`
- Create: `backend/app/road_network/sqlalchemy_repository.py`
- Create: `backend/tests/road_network/test_dijkstra.py`
- Create: `backend/tests/road_network/test_sqlalchemy_repository.py`

**Interfaces:**
- Produces `RouteObjective = Literal["FASTEST", "SHORTEST", "SAFEST"]`.
- Produces `RoadNetworkSnapshot(version, nodes, edges)` and `PathResult(objective, node_ids, edge_ids, distance_km, estimated_minutes, risk_cost, visited_node_count)`.
- Produces `RoadNetworkProvider.snapshot() -> RoadNetworkSnapshot`.
- Produces `PathFinder.find(snapshot, start_node_id, end_node_id, objective, vehicle_weight_tons, excluded_edge_ids=frozenset()) -> PathResult | None`.

- [ ] **Step 1: Write the failing algorithm tests**

```python
from decimal import Decimal

from app.road_network.dijkstra import DijkstraPathFinder
from app.road_network.models import RouteObjective
from app.sandtable.seed_data import ROAD_EDGES, ROAD_NODES


def test_dijkstra_uses_original_new_road_when_open(snapshot) -> None:
    result = DijkstraPathFinder().find(snapshot, "N01", "N06", RouteObjective.FASTEST, Decimal("2.00"))
    assert result is not None
    assert result.edge_ids == ("E01", "E02", "E03", "E04", "E05")
    assert (result.distance_km, result.estimated_minutes) == (Decimal("10.00"), 20)


def test_dijkstra_removes_blocked_edge_and_calculates_detour(snapshot) -> None:
    result = DijkstraPathFinder().find(
        snapshot, "N01", "N06", RouteObjective.FASTEST, Decimal("2.00"), frozenset({"E04"})
    )
    assert result is not None
    assert result.edge_ids == ("E01", "E06", "E07", "E08", "E09")
    assert (result.distance_km, result.estimated_minutes) == (Decimal("13.20"), 24)
    assert "E04" not in result.edge_ids
```

Also test `CONGESTED` multiplication, `BLOCKED` exclusion, `RESTRICTED` weight checks, disconnected graphs, bidirectional traversal, and deterministic lexical tie-breaking.

- [ ] **Step 2: Run and observe failure**

```powershell
& .\.venv\Scripts\python.exe -m pytest backend/tests/road_network -q
```

Expected: FAIL because the road-network package is absent.

- [ ] **Step 3: Implement immutable graph DTOs and provider**

Quantize distances to `Decimal("0.01")`. Build the snapshot from a single database read boundary and compute `version = max(edge.version)`. Return tuples sorted by `node_id` and `edge_id` so graph iteration is stable.

- [ ] **Step 4: Implement Dijkstra without adding a dependency**

Use `heapq` and store `(cost, edge_id_path, node_id)` so equal-cost paths resolve lexically. Build both directions for `bidirectional` edges. Reject blocked edges before enqueueing.

```python
def _weight(edge: RoadEdgeSnapshot, objective: RouteObjective) -> Decimal:
    if objective == "SHORTEST":
        return edge.distance_km
    minutes = Decimal(edge.base_minutes) * edge.congestion_factor
    if objective == "FASTEST":
        return minutes
    risk = {"LOW": Decimal("0"), "MEDIUM": Decimal("4"), "HIGH": Decimal("12")}[edge.risk_level]
    return minutes + risk
```

Return `visited_node_count` as the number of nodes popped with their current best cost. Compute displayed minutes by summing `base_minutes × congestion_factor` and rounding up to the next integer.

- [ ] **Step 5: Run tests and inspect diff**

```powershell
& .\.venv\Scripts\python.exe -m pytest backend/tests/road_network -q
git diff -- backend/app/road_network backend/tests/road_network
git diff --check -- backend/app/road_network backend/tests/road_network
```

Expected: PASS with the exact 10.00/20 and 13.20/24 paths.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/road_network/__init__.py backend/app/road_network/models.py backend/app/road_network/protocols.py backend/app/road_network/dijkstra.py backend/app/road_network/sqlalchemy_repository.py backend/tests/road_network/test_dijkstra.py backend/tests/road_network/test_sqlalchemy_repository.py
git commit -m "feat: calculate offline routes with dijkstra"
```

---

### Task 4: Calculate Replacement Vehicle Assignments

**Files:**
- Create: `backend/app/fleet/__init__.py`
- Create: `backend/app/fleet/models.py`
- Create: `backend/app/fleet/protocols.py`
- Create: `backend/app/fleet/sqlalchemy_repository.py`
- Create: `backend/app/fleet/service.py`
- Create: `backend/tests/fleet/test_allocation_service.py`
- Create: `backend/tests/fleet/test_sqlalchemy_repository.py`

**Interfaces:**
- Produces `VehicleCandidate` with identifiers, availability, remaining load, pickup path, score components, final score, eligibility, and all exclusion reasons.
- Produces `FleetAllocationResult(original_vehicle_id, candidates, selected_vehicle_id, selected_driver_id, pickup_route, vehicle_reassigned, status, reason)`.
- Produces `FleetProvider.list_candidates(excluding_vehicle_id: str) -> tuple[FleetVehicleSnapshot, ...]`.
- Produces `TravelTimeEstimator.estimate(from_node_id, to_node_id, vehicle_weight_tons) -> PathResult | None`.
- Produces `FleetAllocationService.allocate(request: FleetAllocationRequest) -> FleetAllocationResult`.

- [ ] **Step 1: Write failing filter and score tests**

```python
def test_cold_chain_breakdown_selects_v005_with_explainable_score(service, request) -> None:
    result = service.allocate(request)
    selected = next(item for item in result.candidates if item.vehicle_id == "V-005")
    rejected_v003 = next(item for item in result.candidates if item.vehicle_id == "V-003")
    rejected_v011 = next(item for item in result.candidates if item.vehicle_id == "V-011")

    assert (result.selected_vehicle_id, result.selected_driver_id) == ("V-005", "D-003")
    assert (selected.pickup_distance_km, selected.pickup_eta_minutes, selected.score) == (Decimal("2.80"), 6, Decimal("93.4"))
    assert {"CARGO_CAPABILITY_MISMATCH", "INSUFFICIENT_CAPACITY"} <= set(rejected_v003.exclusion_reasons)
    assert {"INSUFFICIENT_CAPACITY", "DRIVER_UNAVAILABLE"} <= set(rejected_v011.exclusion_reasons)
```

Add tests for original-vehicle exclusion, non-available vehicles, license mismatch, unreachable pickup, road-weight restriction, all-rejected `NO_REPLACEMENT_VEHICLE`, and stable tie ordering.

- [ ] **Step 2: Run and observe failure**

```powershell
& .\.venv\Scripts\python.exe -m pytest backend/tests/fleet -q
```

Expected: FAIL because fleet allocation does not exist.

- [ ] **Step 3: Implement the narrow repository and estimator adapter**

The SQLAlchemy repository maps ORM rows to immutable snapshots and closes its session before returning. Implement `DijkstraTravelTimeEstimator` in `fleet/service.py` using only `RoadNetworkProvider` and `PathFinder` interfaces; do not import SQLAlchemy.

- [ ] **Step 4: Implement hard filters and `FLEET_SCORE_V1`**

Collect every applicable exclusion reason in the fixed order from Spec Section 9. Only run path estimation after cheap state/driver/load/cargo checks pass. For eligible rows compute:

```python
score = (
    Decimal("100")
    - Decimal(pickup.estimated_minutes) * Decimal("1.5")
    - pickup.distance_km * Decimal("2")
    - vehicle.current_load_ratio * Decimal("20")
    - road_risk_penalty
    + same_station_bonus
    + cargo_exact_match_bonus
).quantize(Decimal("0.1"))
```

Sort eligible candidates by `(-score, pickup_eta_minutes, vehicle_id)` and append rejected candidates by `vehicle_id`. Return all candidates for evidence, not only eligible ones.

- [ ] **Step 5: Run tests and inspect diff**

```powershell
& .\.venv\Scripts\python.exe -m pytest backend/tests/fleet -q
git diff -- backend/app/fleet backend/tests/fleet
git diff --check -- backend/app/fleet backend/tests/fleet
```

Expected: PASS and V-005 score is exactly 93.4.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/fleet/__init__.py backend/app/fleet/models.py backend/app/fleet/protocols.py backend/app/fleet/sqlalchemy_repository.py backend/app/fleet/service.py backend/tests/fleet/test_allocation_service.py backend/tests/fleet/test_sqlalchemy_repository.py
git commit -m "feat: score replacement fleet vehicles"
```

---

### Task 5: Integrate Sandtable, Fleet, and Route Computation into the Eight-Agent Graph

**Files:**
- Modify: `backend/app/graph/state.py`
- Modify: `backend/app/graph/dependencies.py`
- Modify: `backend/app/graph/builder.py`
- Modify: `backend/app/agents/intake.py`
- Modify: `backend/app/agents/capacity.py`
- Modify: `backend/app/agents/routing.py`
- Modify: `backend/app/capacity/models.py`
- Modify: `backend/app/routing/models.py`
- Modify: `backend/app/routing/service.py`
- Modify: `backend/app/runtime.py`
- Modify: `backend/tests/graph/test_capacity_agent.py`
- Modify: `backend/tests/graph/test_routing_agent.py`
- Modify: `backend/tests/unit/test_routing.py`
- Create: `backend/tests/graph/test_offline_dispatch_flow.py`

**Interfaces:**
- `GraphDependencies` gains `sandtable_context_service` and `fleet_allocation_service` while keeping the eight-node order unchanged.
- `DispatchGraphState` gains the exact fields listed in Spec Section 11, including `road_network_nodes` and `road_network_edges` for backend-sourced drawing.
- `RoutingService.plan(context, capacity_state, affected_edge_ids, memory_results) -> RoutingResult` produces original, pickup, candidate, and recommended paths.

- [ ] **Step 1: Write the failing vehicle-breakdown graph test**

```python
@pytest.mark.asyncio
async def test_vehicle_breakdown_reassigns_vehicle_and_continues_to_routing(graph, breakdown_state) -> None:
    result = await graph.ainvoke(breakdown_state)
    assert result["capacity_state"]["capacity_status"] == "REASSIGNED"
    assert result["selected_vehicle_id"] == "V-005"
    assert result["selected_driver_id"] == "D-003"
    assert result["vehicle_reassigned"] is True
    assert result["pickup_route"]["edge_ids"] == ["E20"]
    assert result["recommended_path"]["node_ids"][-1] == "N06"
    assert result["requires_manual_review"] is False
```

- [ ] **Step 2: Write the failing road-block graph test**

```python
@pytest.mark.asyncio
async def test_road_block_replans_without_e04(graph, blocked_state) -> None:
    result = await graph.ainvoke(blocked_state)
    assert result["blocked_edge_ids"] == ["E04"]
    assert result["original_path"]["edge_ids"] == ["E01", "E02", "E03", "E04", "E05"]
    assert result["recommended_path"]["edge_ids"] == ["E01", "E06", "E07", "E08", "E09"]
    assert result["distance_delta_km"] == "3.20"
    assert result["eta_delta_minutes"] == 4
    assert result["routing_algorithm"] == "DIJKSTRA_V1"
```

- [ ] **Step 3: Run the focused tests and confirm failure**

```powershell
& .\.venv\Scripts\python.exe -m pytest backend/tests/graph/test_offline_dispatch_flow.py -q
```

Expected: FAIL because graph state and agents do not expose the new fields.

- [ ] **Step 4: Enrich intake through a narrow service**

Change `intake_node` to accept an optional `SandtableContextService`. Preserve current validation when it is absent for isolated tests. When present, load order context and resolve the incident. Map `RoadLocationUnresolved` to:

```python
{
    "requires_manual_review": True,
    "error_code": "ROAD_LOCATION_UNRESOLVED",
    "error_message": "The reported road location could not be resolved uniquely.",
}
```

Write cargo, origin/destination nodes, incident node, affected edges, and road-network version into state.

- [ ] **Step 5: Make capacity reassign rather than stop**

For broken/unavailable/maintenance original vehicles, call `FleetAllocationService.allocate`. Convert candidates to JSON-safe graph state. If a target exists, set `capacity_status="REASSIGNED"`, `vehicle_available=True`, selected IDs, pickup route, and `requires_manual_review=False`. If none exists, set `NO_REPLACEMENT_VEHICLE` and manual review. Normal vehicles retain existing capacity evaluation behavior.

- [ ] **Step 6: Replace static candidate selection with offline route calculation**

`RoutingService.plan` computes the original FASTEST route with the affected edge temporarily available, then computes FASTEST/SHORTEST/SAFEST with current exclusions. Deduplicate by edge sequence, assign `RTE-` plus the first 16 uppercase hexadecimal characters of `sha256("|".join(edge_ids))`, calculate `ROUTE_SCORE_V1`, and choose by the deterministic order in the spec. For breakdowns, route from the incident node to the destination and include the fleet pickup path separately.

Do not let `IssueRecommendationService` reject a route solely because the original vehicle is broken when `capacity_status == "REASSIGNED"`.

- [ ] **Step 7: Wire MySQL-backed services in Docker development runtime**

Construct `SqlAlchemySandtableRepository`, `SqlAlchemyRoadNetworkRepository`, `SqlAlchemyFleetRepository`, `DijkstraPathFinder`, `FleetAllocationService`, and the updated `RoutingService` from `session_factory`. Remove `InMemoryRouteProvider.default_catalog()` and generated in-memory capacity records from the Docker runtime path; retain test doubles only in tests.

- [ ] **Step 8: Run graph regression tests**

```powershell
& .\.venv\Scripts\python.exe -m pytest backend/tests/graph/test_capacity_agent.py backend/tests/graph/test_routing_agent.py backend/tests/graph/test_offline_dispatch_flow.py backend/tests/unit/test_capacity.py backend/tests/unit/test_routing.py -q
```

Expected: PASS; existing non-sandtable tests still use injected doubles.

- [ ] **Step 9: Inspect and commit**

```powershell
git diff -- backend/app/graph backend/app/agents backend/app/capacity backend/app/routing backend/app/runtime.py backend/tests/graph backend/tests/unit/test_capacity.py backend/tests/unit/test_routing.py
git diff --check -- backend/app/graph backend/app/agents backend/app/capacity backend/app/routing backend/app/runtime.py
git add backend/app/graph/state.py backend/app/graph/dependencies.py backend/app/graph/builder.py backend/app/agents/intake.py backend/app/agents/capacity.py backend/app/agents/routing.py backend/app/capacity/models.py backend/app/routing/models.py backend/app/routing/service.py backend/app/runtime.py backend/tests/graph/test_capacity_agent.py backend/tests/graph/test_routing_agent.py backend/tests/graph/test_offline_dispatch_flow.py backend/tests/unit/test_capacity.py backend/tests/unit/test_routing.py
git commit -m "feat: run fleet and route calculations in agent graph"
```

---

### Task 6: Atomically Reserve Vehicles and Persist Dispatch Evidence

**Files:**
- Modify: `backend/app/dispatch/models.py`
- Modify: `backend/app/dispatch/service.py`
- Modify: `backend/app/agents/dispatch.py`
- Modify: `backend/app/audit/models.py`
- Modify: `backend/app/audit/service.py`
- Modify: `backend/app/agents/audit.py`
- Modify: `backend/app/publications/service.py`
- Modify: `backend/tests/unit/test_dispatch_service.py`
- Modify: `backend/tests/unit/test_audit_service.py`
- Create: `backend/tests/concurrency/test_vehicle_reservation.py`
- Modify: `backend/tests/publications/test_service.py`

**Interfaces:**
- `DispatchService.execute` accepts `original_vehicle_id`, ordered `candidate_vehicles`, `transfer_node_id`, `fleet_evidence`, and `route_evidence`; the target driver comes from the candidate that is successfully reserved.
- `DispatchResultState` returns original/target vehicle and target driver.
- `AuditChecks` gains `vehicle_assignment`, `capacity_constraint`, `route_connectivity`, and `blocked_edge_exclusion`.

- [ ] **Step 1: Write the failing persistence test**

```python
def test_dispatch_reserves_replacement_and_persists_two_evidence_rows(service, factory, task) -> None:
    result = service.execute(**breakdown_execution_args(task.task_id))
    with factory() as session:
        vehicle = session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == "V-005"))
        dispatch = session.get(Dispatch, result.dispatch_id)
        evidence = session.scalars(select(DispatchEvidence).where(DispatchEvidence.dispatch_id == dispatch.id)).all()
    assert (vehicle.status, dispatch.original_vehicle_id, dispatch.target_vehicle_id) == ("RESERVED", "V-001", "V-005")
    assert dispatch.target_driver_id == "D-003"
    assert {item.evidence_type for item in evidence} == {"FLEET_ALLOCATION", "ROUTE_CALCULATION"}
```

- [ ] **Step 2: Write the failing concurrency test**

Create two tasks and two eligible cold-chain candidates. Start two sessions from a barrier so both prefer V-005. Assert one dispatch reserves V-005 and the other tries the next ranked eligible vehicle once; assert no vehicle is reserved by two tasks and every successful dispatch has exactly two evidence rows. When no second candidate exists, assert `VEHICLE_RESERVATION_CONFLICT` leads to review.

- [ ] **Step 3: Run and observe failure**

```powershell
& .\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_dispatch_service.py backend/tests/concurrency/test_vehicle_reservation.py -q
```

Expected: FAIL because dispatch does not persist vehicle or evidence data.

- [ ] **Step 4: Implement ranked optimistic reservation**

Within a transaction, load the selected `FleetVehicle`, verify `AVAILABLE`, set `RESERVED`, add `Dispatch`, flush, add both `DispatchEvidence` rows, and commit. On `StaleDataError`, roll back and try the next eligible candidate once. Convert a second conflict to `VehicleReservationConflict`. Never compare a caller-supplied version in Python as a substitute for `version_id_col`.

Keep task replay idempotent: if a dispatch already exists for `task_id`, return its persisted target vehicle and do not reserve another vehicle or add duplicate evidence.

- [ ] **Step 5: Extend audit checks**

For breakdowns, require target vehicle different from original, selected candidate eligible, remaining capacity sufficient, and cargo capability compatible. For road blocks, require every recommended edge to exist, connect in sequence, and exclude all `blocked_edge_ids`. Persist compact candidate IDs/scores/reasons and path IDs; do not store secrets or raw authorization data.

- [ ] **Step 6: Extend publication instruction**

For a vehicle reassignment, produce a deterministic instruction containing target plate, target driver, pickup node, and route. Preserve the existing action-only publication behavior and existing permission checks.

- [ ] **Step 7: Run focused service tests**

```powershell
& .\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_dispatch_service.py backend/tests/unit/test_audit_service.py backend/tests/concurrency/test_vehicle_reservation.py -q
```

Expected: PASS.

- [ ] **Step 8: Inspect and commit**

```powershell
git diff -- backend/app/dispatch backend/app/agents/dispatch.py backend/app/audit backend/app/agents/audit.py backend/app/publications backend/tests/unit backend/tests/concurrency/test_vehicle_reservation.py
git diff --check -- backend/app/dispatch backend/app/audit backend/app/publications
git add backend/app/dispatch/models.py backend/app/dispatch/service.py backend/app/agents/dispatch.py backend/app/audit/models.py backend/app/audit/service.py backend/app/agents/audit.py backend/app/publications/service.py backend/tests/unit/test_dispatch_service.py backend/tests/unit/test_audit_service.py backend/tests/concurrency/test_vehicle_reservation.py backend/tests/publications/test_service.py
git commit -m "feat: persist atomic fleet rerouting decisions"
```

---

### Task 7: Expose Fleet and Route Evidence Through Events and Result API

**Files:**
- Modify: `backend/app/events/graph_adapter.py`
- Modify: `backend/app/api/v1/schemas.py`
- Modify: `backend/app/services/dispatch_task_api_service.py`
- Modify: `backend/tests/api/test_task_events.py`
- Modify: `backend/tests/api/test_dispatch_tasks.py`
- Modify: `backend/tests/api/test_dispatch_api_e2e.py`
- Modify: `backend/tests/api/test_task_websocket.py`

**Interfaces:**
- Produces Pydantic `VehicleCandidateResponse`, `VehicleAllocationResponse`, `RoadNodeResponse`, `RoadEdgeResponse`, `PathResponse`, `RouteCandidateResponse`, and `RoutePlanResponse`; `RoutePlanResponse` includes complete `network_nodes` and `network_edges`.
- Extends `TaskResultResponse` with nullable `vehicle_allocation` and `route_plan`.

- [ ] **Step 1: Write failing event assertions**

```python
assert capacity_event.data["selected_vehicle_id"] == "V-005"
assert capacity_event.data["selected_driver_id"] == "D-003"
assert capacity_event.data["vehicle_reassigned"] is True
assert len(capacity_event.data["candidate_vehicles"]) == 11

assert routing_event.data["algorithm"] == "DIJKSTRA_V1"
assert routing_event.data["blocked_edge_ids"] == ["E04"]
assert routing_event.data["recommended_path"]["edge_ids"] == ["E01", "E06", "E07", "E08", "E09"]
```

- [ ] **Step 2: Write the failing result API test**

```python
response = client.get(f"/api/v1/dispatch-tasks/{task_id}/result", headers=supervisor_headers)
body = response.json()
assert body["vehicle_allocation"]["target_vehicle_id"] == "V-005"
assert body["vehicle_allocation"]["pickup_route"]["edge_ids"] == ["E20"]
assert body["route_plan"]["distance_delta_km"] == "3.20"
assert "E04" not in body["route_plan"]["recommended_path"]["edge_ids"]
```

Also assert an employee cannot see unpublished vehicle/route details, matching existing route visibility behavior.

- [ ] **Step 3: Run and observe failure**

```powershell
& .\.venv\Scripts\python.exe -m pytest backend/tests/api/test_task_events.py backend/tests/api/test_dispatch_tasks.py backend/tests/api/test_dispatch_api_e2e.py -q
```

Expected: FAIL because events and result schemas omit the evidence.

- [ ] **Step 4: Extend graph event payloads**

For `capacity`, include candidate/selection keys from the node patch plus the legacy capacity fields. For `routing`, include original/recommended paths, candidate routes, blocked edges, deltas, visited count, algorithm, version, `network_nodes`, and `network_edges`. For `dispatch`, add vehicle and driver identifiers. Keep payloads JSON-safe by serializing Decimal values as fixed strings.

- [ ] **Step 5: Read evidence rows in the task result service**

Query both `DispatchEvidence` rows with the dispatch inside the result session, validate payload dictionaries, and map them into explicit Pydantic response models. Do not return arbitrary unvalidated JSON directly. Apply `route_visible` to both new response blocks.

- [ ] **Step 6: Run API and WebSocket tests**

```powershell
& .\.venv\Scripts\python.exe -m pytest backend/tests/api/test_task_events.py backend/tests/api/test_dispatch_tasks.py backend/tests/api/test_dispatch_api_e2e.py backend/tests/api/test_task_websocket.py -q
```

Expected: PASS.

- [ ] **Step 7: Inspect and commit**

```powershell
git diff -- backend/app/events/graph_adapter.py backend/app/api/v1/schemas.py backend/app/services/dispatch_task_api_service.py backend/tests/api
git diff --check -- backend/app/events/graph_adapter.py backend/app/api/v1/schemas.py backend/app/services/dispatch_task_api_service.py
git add backend/app/events/graph_adapter.py backend/app/api/v1/schemas.py backend/app/services/dispatch_task_api_service.py backend/tests/api/test_task_events.py backend/tests/api/test_dispatch_tasks.py backend/tests/api/test_dispatch_api_e2e.py backend/tests/api/test_task_websocket.py
git commit -m "feat: expose fleet and route calculation evidence"
```

---

### Task 8: Render Vehicle Reassignment and a Dynamic Road Map

**Files:**
- Create: `frontend/src/components/fleet-allocation-panel.tsx`
- Create: `frontend/tests/fleet-allocation-panel.test.tsx`
- Create: `frontend/tests/dynamic-route-visual.test.tsx`
- Modify: `frontend/src/types/dispatch.ts`
- Modify: `frontend/src/services/api/dispatch-adapter.ts`
- Modify: `frontend/src/components/capacity-evidence-panel.tsx`
- Modify: `frontend/src/components/routing-evidence-panel.tsx`
- Modify: `frontend/src/components/route-visual.tsx`
- Modify: `frontend/src/pages/api-dispatch-detail-page.tsx`
- Modify: `frontend/src/utils/presentation-labels.ts`
- Modify: `frontend/src/styles/index.css`
- Modify: `frontend/tests/api-dispatch-adapter.test.ts`
- Modify: `frontend/tests/dispatch-v2-evidence.test.tsx`

**Interfaces:**
- TypeScript mirrors backend `VehicleAllocationResponse` and `RoutePlanResponse` exactly.
- `FleetAllocationPanel` consumes `VehicleAllocationResponse` only.
- `RouteVisual` consumes `RoutePlanResponse` and has no hard-coded road names or paths.

- [ ] **Step 1: Write the failing vehicle panel test**

```typescript
it("shows the selected replacement and every rejection reason", async () => {
  const { container } = await render(<FleetAllocationPanel allocation={breakdownAllocation} />);
  expect(container.textContent).toContain("新物冷链-01");
  expect(container.textContent).toContain("新物冷链-05");
  expect(container.textContent).toContain("93.4");
  expect(container.textContent).toContain("剩余载重不足");
  expect(container.textContent).toContain("不支持冷链");
  expect(container.textContent).toContain("接驳 2.80 公里 · 6 分钟");
});
```

- [ ] **Step 2: Write the failing dynamic SVG test**

```typescript
it("draws the blocked edge and calculated detour from API coordinates", async () => {
  const { container } = await render(<RouteVisual plan={blockedRoutePlan} />);
  expect(container.querySelector('[data-edge-id="E04"]')).toHaveClass("route-edge-blocked");
  expect(container.querySelector('[data-edge-id="E07"]')).toHaveClass("route-edge-recommended");
  expect(container.textContent).toContain("Dijkstra");
  expect(container.textContent).toContain("+3.20 公里");
  expect(container.textContent).toContain("+4 分钟");
});
```

- [ ] **Step 3: Run and observe failure**

From `frontend/`:

```powershell
npm.cmd test -- --run tests/fleet-allocation-panel.test.tsx tests/dynamic-route-visual.test.tsx
```

Expected: FAIL because the typed panels and dynamic route inputs do not exist.

- [ ] **Step 4: Add exact API types and adapter fixtures**

Use string types for backend decimals. Model node/edge IDs as strings and statuses/objectives as string unions. Extend adapter tests to assert both new blocks are preserved without renaming IDs or converting decimal strings to floating-point values.

- [ ] **Step 5: Implement the fleet panel**

Render the original broken vehicle card, selected target card, arrow, pickup metrics, and a semantic candidate table. Render every exclusion reason with localized labels. Use `data-vehicle-id` for stable tests and accessible row headings for plate numbers.

- [ ] **Step 6: Replace the fixed SVG with data-driven geometry**

Compute an SVG viewBox from returned node coordinates with fixed padding. Render each road once and assign classes by precedence: blocked, pickup, recommended, original, normal. Render labels from response data and a `<title>` per edge. Preserve a compact prop only if current callers require it; remove every fixed `d=` path and hard-coded `102国道`/`新平路` label.

- [ ] **Step 7: Integrate panels into the API detail page**

When `result.vehicle_allocation` exists, render `FleetAllocationPanel`. When `result.route_plan` exists, render `RouteVisual` plus the calculation trace showing algorithm, network version, blocked edges, visited nodes, node sequence, edge sequence, candidate objectives, and new/old comparison. Keep event panels for in-flight progress and result panels for durable post-refresh evidence.

- [ ] **Step 8: Run focused frontend tests**

```powershell
npm.cmd test -- --run tests/fleet-allocation-panel.test.tsx tests/dynamic-route-visual.test.tsx tests/api-dispatch-adapter.test.ts tests/dispatch-v2-evidence.test.tsx tests/task-events-lifecycle.test.tsx
```

Expected: PASS; eight `.pipeline-item` elements remain unchanged.

- [ ] **Step 9: Inspect and commit**

```powershell
git diff -- frontend/src/types/dispatch.ts frontend/src/services/api/dispatch-adapter.ts frontend/src/components frontend/src/pages/api-dispatch-detail-page.tsx frontend/src/utils/presentation-labels.ts frontend/src/styles/index.css frontend/tests
git diff --check -- frontend/src frontend/tests
git add frontend/src/types/dispatch.ts frontend/src/services/api/dispatch-adapter.ts frontend/src/components/fleet-allocation-panel.tsx frontend/src/components/capacity-evidence-panel.tsx frontend/src/components/routing-evidence-panel.tsx frontend/src/components/route-visual.tsx frontend/src/pages/api-dispatch-detail-page.tsx frontend/src/utils/presentation-labels.ts frontend/src/styles/index.css frontend/tests/fleet-allocation-panel.test.tsx frontend/tests/dynamic-route-visual.test.tsx frontend/tests/api-dispatch-adapter.test.ts frontend/tests/dispatch-v2-evidence.test.tsx
git commit -m "feat: visualize vehicle reassignment and rerouting"
```

---

### Task 9: Verify Both Teacher-Feedback Scenarios End to End

**Files:**
- Create: `scripts/offline_fleet_routing_acceptance.py`
- Create: `scripts/test-offline-fleet-routing.ps1`
- Create: `frontend/e2e/offline-fleet-rerouting.spec.ts`
- Modify: `scripts/test-docker.ps1`
- Modify only after successful evidence: `docs/final/FINAL_FACTS.md`, `docs/final/COUNTYFLOW_END_TO_END_FLOW_REPORT.md`, and `README.md`

**Interfaces:**
- Acceptance script submits `DEMO-ORDER-001` breakdown and `DEMO-ORDER-005` road-block tasks through the real API and polls only public task endpoints.
- Browser test proves the durable results are visible after refresh.

- [ ] **Step 1: Write the failing black-box acceptance script**

The script must assert:

```python
assert breakdown["vehicle_allocation"]["original_vehicle_id"] == "V-001"
assert breakdown["vehicle_allocation"]["target_vehicle_id"] == "V-005"
assert breakdown["vehicle_allocation"]["target_driver_id"] == "D-003"
assert breakdown["vehicle_allocation"]["pickup_route"]["edge_ids"] == ["E20"]

assert blocked["route_plan"]["original_path"]["edge_ids"] == ["E01", "E02", "E03", "E04", "E05"]
assert blocked["route_plan"]["recommended_path"]["edge_ids"] == ["E01", "E06", "E07", "E08", "E09"]
assert blocked["route_plan"]["distance_delta_km"] == "3.20"
assert blocked["route_plan"]["eta_delta_minutes"] == 4
```

Also query MySQL through the existing Docker helper pattern and assert one dispatch, two evidence rows, one reserved V-005, and no pending Redis messages for each task.

- [ ] **Step 2: Run against the current stack and confirm failure**

```powershell
& .\scripts\test-offline-fleet-routing.ps1
```

Expected before implementation: FAIL because the new evidence fields and tables are absent. If the Docker stack is not running, record BLOCKED BY ENVIRONMENT rather than treating that as the expected application failure.

- [ ] **Step 3: Add the Playwright scenario**

Use the existing authenticated API helpers. Submit each issue through the visible report UI, open the generated task, and assert the selected vehicle, rejected reasons, blocked red edge, green E07 detour, `+3.20 公里`, `+4 分钟`, and Dijkstra trace. Reload the page and repeat the durable-result assertions.

- [ ] **Step 4: Run targeted backend verification**

```powershell
& .\.venv\Scripts\python.exe -m ruff check backend
& .\.venv\Scripts\python.exe -m pytest backend/tests/migrations/test_offline_fleet_routing_migration.py backend/tests/sandtable backend/tests/road_network backend/tests/fleet backend/tests/graph/test_offline_dispatch_flow.py backend/tests/concurrency/test_vehicle_reservation.py backend/tests/api/test_task_events.py backend/tests/api/test_dispatch_tasks.py -q
```

Expected: PASS.

- [ ] **Step 5: Run full backend and frontend gates**

```powershell
& .\scripts\test.ps1
& .\scripts\lint.ps1
Push-Location frontend
npm.cmd test
npm.cmd run lint
npm.cmd run build
Pop-Location
```

Expected: all commands exit 0.

- [ ] **Step 6: Run Docker and browser acceptance**

```powershell
& .\scripts\test-offline-fleet-routing.ps1
Push-Location frontend
npx.cmd playwright test e2e/offline-fleet-rerouting.spec.ts
Pop-Location
```

Expected: both black-box scenarios and Playwright pass. If infrastructure is unavailable, preserve the tests and report the exact command as not re-verified.

- [ ] **Step 7: Perform final diff and secret scans**

```powershell
rg -n "(api[_-]?key|authorization|bearer)\s*[:=]\s*['\"]" backend/app frontend/src scripts/offline_fleet_routing_acceptance.py
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' diff --check
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' diff --cached --check
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' status --short --branch
```

Expected: no hard-coded secret matches and no whitespace errors. Existing unrelated changes remain untouched.

- [ ] **Step 8: Update factual documentation from actual output and commit**

Record only commands that ran and their real totals. Add the two scenario facts, algorithm versions, seed counts, and known offline-only limitation. Do not claim real maps or live vehicle systems.

```powershell
git add scripts/offline_fleet_routing_acceptance.py scripts/test-offline-fleet-routing.ps1 scripts/test-docker.ps1 frontend/e2e/offline-fleet-rerouting.spec.ts README.md docs/final/FINAL_FACTS.md docs/final/COUNTYFLOW_END_TO_END_FLOW_REPORT.md
git commit -m "test: verify offline fleet rerouting scenarios"
```

---

## Implementation Completion Checklist

- [ ] MySQL contains exactly the approved 8 stations, 18 nodes, 26 edges, 10 drivers, 12 vehicles, and 12 new-county orders after repeated seed runs.
- [ ] Vehicle breakdown produces V-001→V-005 and D-003 with an E20 pickup path and score 93.4.
- [ ] Road blockage excludes E04 and calculates E01→E06→E07→E08→E09 at 13.20 km and 24 minutes.
- [ ] All candidate vehicles retain localized eligibility or exclusion evidence.
- [ ] Original, pickup, candidate, and selected route paths are durable and survive refresh.
- [ ] Vehicle reservation and evidence persistence are atomic and idempotent.
- [ ] The eight-agent order, checkpoint behavior, worker retry/recovery, and post-persistence `XACK` remain intact.
- [ ] API permissions hide unpublished assignment and route evidence from delivery employees.
- [ ] Frontend map geometry comes entirely from API coordinates and path IDs.
- [ ] Targeted tests, full backend tests, frontend test/lint/build, Docker acceptance, and Playwright results are recorded honestly.
- [ ] Final `git diff --check` output is clean.
