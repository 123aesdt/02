from decimal import Decimal

import pytest

from app.fleet.models import FleetAllocationRequest, FleetDriverSnapshot, FleetVehicleSnapshot
from app.fleet.service import DijkstraTravelTimeEstimator, FleetAllocationService
from app.road_network.dijkstra import DijkstraPathFinder
from app.road_network.models import PathResult, RoadEdgeSnapshot, RoadNetworkSnapshot, RoadNodeSnapshot, RouteObjective
from app.sandtable.seed_data import ROAD_EDGES, ROAD_NODES

_DEFAULT_DRIVER = object()


def _driver(driver_id: str = "D-003", *, status: str = "ON_DUTY", license_class: str = "C1") -> FleetDriverSnapshot:
    return FleetDriverSnapshot(driver_id=driver_id, name=driver_id, license_class=license_class, status=status, current_node_id="N15")


def _vehicle(
    vehicle_id: str,
    *,
    status: str = "AVAILABLE",
    vehicle_type: str = "REFRIGERATED_VAN",
    max_load_kg: str = "1000.00",
    current_load_kg: str = "100.00",
    cargo_capability: str = "COLD_CHAIN",
    gross_weight_tons: str = "2.40",
    current_node_id: str = "N15",
    driver: FleetDriverSnapshot | None | object = _DEFAULT_DRIVER,
) -> FleetVehicleSnapshot:
    return FleetVehicleSnapshot(
        vehicle_id=vehicle_id,
        plate_no=vehicle_id,
        vehicle_type=vehicle_type,
        max_load_kg=Decimal(max_load_kg),
        current_load_kg=Decimal(current_load_kg),
        cargo_capability=cargo_capability,
        gross_weight_tons=Decimal(gross_weight_tons),
        status=status,
        current_node_id=current_node_id,
        driver=_driver(f"D-{vehicle_id[-3:]}") if driver is _DEFAULT_DRIVER else driver,
    )


def _path(*, distance: str = "2.80", minutes: int = 6, risk: str = "0") -> PathResult:
    return PathResult(RouteObjective.FASTEST, ("N15", "N04"), ("E20",), Decimal(distance), minutes, Decimal(risk), 2)


class _FleetProvider:
    def __init__(self, candidates: tuple[FleetVehicleSnapshot, ...]) -> None:
        self._candidates = candidates

    def list_candidates(self, excluding_vehicle_id: str) -> tuple[FleetVehicleSnapshot, ...]:
        return self._candidates


class _Estimator:
    def __init__(self, paths: dict[str, PathResult | None], *, restricted_nodes: frozenset[str] = frozenset()) -> None:
        self.paths = paths
        self.restricted_nodes = restricted_nodes
        self.calls: list[str] = []

    def estimate(self, from_node_id: str, to_node_id: str, vehicle_weight_tons: Decimal) -> PathResult | None:
        self.calls.append(from_node_id)
        return self.paths.get(from_node_id)

    def is_weight_restricted(self, from_node_id: str, to_node_id: str, vehicle_weight_tons: Decimal) -> bool:
        return from_node_id in self.restricted_nodes


def _request() -> FleetAllocationRequest:
    return FleetAllocationRequest(
        original_vehicle_id="V-001",
        incident_node_id="N04",
        cargo_weight_kg=Decimal("700.00"),
        cargo_type="COLD_CHAIN",
    )


def _service(
    candidates: tuple[FleetVehicleSnapshot, ...], paths: dict[str, PathResult | None], *, restricted_nodes: frozenset[str] = frozenset()
) -> tuple[FleetAllocationService, _Estimator]:
    estimator = _Estimator(paths, restricted_nodes=restricted_nodes)
    return FleetAllocationService(_FleetProvider(candidates), estimator), estimator


def test_cold_chain_breakdown_selects_v005_with_explainable_score() -> None:
    v001 = _vehicle("V-001", status="BROKEN", driver=_driver("D-001", status="BUSY"))
    v003 = _vehicle("V-003", vehicle_type="VAN", current_load_kg="600.00", cargo_capability="GENERAL", driver=_driver("D-013"))
    v005 = _vehicle("V-005", driver=_driver("D-003"))
    v011 = _vehicle("V-011", current_load_kg="1300.00", driver=None)
    service, _ = _service((v011, v003, v005, v001), {"N15": _path(), "N14": _path(distance="3.00", minutes=7)})

    result = service.allocate(_request())

    selected = next(item for item in result.candidates if item.vehicle_id == "V-005")
    rejected_v003 = next(item for item in result.candidates if item.vehicle_id == "V-003")
    rejected_v011 = next(item for item in result.candidates if item.vehicle_id == "V-011")
    assert (result.selected_vehicle_id, result.selected_driver_id) == ("V-005", "D-003")
    assert selected.pickup_route is not None and selected.pickup_route.edge_ids == ("E20",)
    assert (selected.pickup_distance_km, selected.pickup_eta_minutes, selected.score) == (Decimal("2.80"), 6, Decimal("93.4"))
    assert rejected_v003.exclusion_reasons == ("INSUFFICIENT_CAPACITY", "CARGO_CAPABILITY_MISMATCH")
    assert rejected_v011.exclusion_reasons == ("DRIVER_UNAVAILABLE", "INSUFFICIENT_CAPACITY")


@pytest.mark.parametrize(
    ("vehicle", "expected_reason"),
    [
        (_vehicle("V-001"), "ORIGINAL_VEHICLE_EXCLUDED"),
        (_vehicle("V-020", status="MAINTENANCE"), "VEHICLE_UNAVAILABLE"),
        (_vehicle("V-021", driver=_driver(status="OFF_DUTY")), "DRIVER_UNAVAILABLE"),
        (_vehicle("V-022", vehicle_type="LIGHT_TRUCK", driver=_driver(license_class="C1")), "LICENSE_MISMATCH"),
    ],
)
def test_hard_filters_report_state_and_driver_exclusions(vehicle: FleetVehicleSnapshot, expected_reason: str) -> None:
    service, estimator = _service((vehicle,), {vehicle.current_node_id: _path()})
    candidate = service.allocate(_request()).candidates[0]
    assert expected_reason in candidate.exclusion_reasons
    assert estimator.calls == []


def test_unreachable_and_weight_restricted_pickups_are_distinguished() -> None:
    unreachable = _vehicle("V-030", current_node_id="N30")
    restricted = _vehicle("V-031", current_node_id="N31", gross_weight_tons="5.10")
    service, _ = _service((unreachable, restricted), {"N30": None, "N31": None}, restricted_nodes=frozenset({"N31"}))
    result = service.allocate(_request())
    by_vehicle = {candidate.vehicle_id: candidate for candidate in result.candidates}
    assert by_vehicle["V-030"].exclusion_reasons == ("PICKUP_UNREACHABLE",)
    assert by_vehicle["V-031"].exclusion_reasons == ("ROAD_WEIGHT_RESTRICTION", "PICKUP_UNREACHABLE")


def test_all_rejected_returns_no_replacement_reason() -> None:
    service, _ = _service((_vehicle("V-040", status="RESERVED"),), {})
    result = service.allocate(_request())
    assert (result.status, result.reason, result.vehicle_reassigned, result.selected_vehicle_id) == (
        "UNAVAILABLE",
        "NO_REPLACEMENT_VEHICLE",
        False,
        None,
    )


def test_eligible_ties_are_stable_and_rejected_candidates_follow_by_vehicle_id() -> None:
    v010 = _vehicle("V-010", current_node_id="N10")
    v002 = _vehicle("V-002", current_node_id="N02")
    rejected = _vehicle("V-003", status="BROKEN")
    service, _ = _service((v010, rejected, v002), {"N10": _path(), "N02": _path()})
    result = service.allocate(_request())
    assert [candidate.vehicle_id for candidate in result.candidates] == ["V-002", "V-010", "V-003"]


def _road_snapshot() -> RoadNetworkSnapshot:
    return RoadNetworkSnapshot(
        version=1,
        nodes=tuple(RoadNodeSnapshot(row["node_id"], row["name"], Decimal(row["x_km"]), Decimal(row["y_km"]), row["node_type"]) for row in ROAD_NODES),
        edges=tuple(
            RoadEdgeSnapshot(
                row["edge_id"],
                row["name"],
                row["from_node_id"],
                row["to_node_id"],
                Decimal(row["distance_km"]),
                row["base_minutes"],
                row["road_level"],
                row["risk_level"],
                "OPEN",
                Decimal("1.00"),
                Decimal(row["weight_limit_tons"]),
                True,
                1,
            )
            for row in ROAD_EDGES
        ),
    )


class _RoadProvider:
    def snapshot(self) -> RoadNetworkSnapshot:
        return _road_snapshot()


def test_collects_every_applicable_cheap_exclusion_in_design_order() -> None:
    vehicle = _vehicle(
        "V-001",
        status="MAINTENANCE",
        vehicle_type="LIGHT_TRUCK",
        current_load_kg="900.00",
        cargo_capability="GENERAL",
        driver=_driver(status="OFF_DUTY", license_class="C1"),
    )
    service, estimator = _service((vehicle,), {})
    candidate = service.allocate(_request()).candidates[0]
    assert candidate.exclusion_reasons == (
        "ORIGINAL_VEHICLE_EXCLUDED",
        "VEHICLE_UNAVAILABLE",
        "DRIVER_UNAVAILABLE",
        "LICENSE_MISMATCH",
        "INSUFFICIENT_CAPACITY",
        "CARGO_CAPABILITY_MISMATCH",
    )
    assert estimator.calls == []


def test_b2_driver_satisfies_light_vehicle_license_requirement() -> None:
    vehicle = _vehicle("V-050", vehicle_type="VAN", driver=_driver(license_class="B2"))
    service, _ = _service((vehicle,), {"N15": _path()})
    candidate = service.allocate(_request()).candidates[0]
    assert candidate.eligible is True


class _VersionedRoadProvider:
    def __init__(self) -> None:
        self.calls = 0

    def snapshot(self) -> RoadNetworkSnapshot:
        self.calls += 1
        return RoadNetworkSnapshot(version=self.calls, nodes=(), edges=())


class _VersionRecordingPathFinder:
    def __init__(self) -> None:
        self.snapshot_versions: list[int] = []

    def find(
        self,
        snapshot: RoadNetworkSnapshot,
        start_node_id: str,
        end_node_id: str,
        objective: RouteObjective,
        vehicle_weight_tons: Decimal,
        excluded_edge_ids: frozenset[str] = frozenset(),
    ) -> PathResult:
        self.snapshot_versions.append(snapshot.version)
        return _path()


def test_allocate_freezes_one_road_snapshot_for_all_eligible_candidates() -> None:
    provider = _VersionedRoadProvider()
    finder = _VersionRecordingPathFinder()
    estimator = DijkstraTravelTimeEstimator(provider, finder)
    candidates = (_vehicle("V-060", current_node_id="N60"), _vehicle("V-061", current_node_id="N61"))

    FleetAllocationService(_FleetProvider(candidates), estimator).allocate(_request())

    assert provider.calls == 1
    assert finder.snapshot_versions == [1, 1]


def test_dijkstra_adapter_uses_narrow_road_interfaces_and_returns_e20_pickup() -> None:
    result = DijkstraTravelTimeEstimator(_RoadProvider(), DijkstraPathFinder()).estimate("N15", "N04", Decimal("2.40"))
    assert result is not None
    assert (result.edge_ids, result.distance_km, result.estimated_minutes) == (("E20",), Decimal("2.80"), 6)
