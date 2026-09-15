from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal

_INVALID = object()


def _text(value: object) -> object:
    return value if isinstance(value, str) else _INVALID


def _nullable_text(value: object) -> object:
    return None if value is None else _text(value)


def _boolean(value: object) -> object:
    return value if isinstance(value, bool) else _INVALID


def _integer(value: object) -> object:
    return value if isinstance(value, int) and not isinstance(value, bool) else _INVALID


def _nullable_integer(value: object) -> object:
    return None if value is None else _integer(value)


def _number(value: object) -> object:
    if isinstance(value, bool):
        return _INVALID
    return value if isinstance(value, (str, int, float, Decimal)) else _INVALID


def _nullable_number(value: object) -> object:
    return None if value is None else _number(value)


def _string_list(value: object) -> object:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return _INVALID
    items = list(value)
    return items if all(isinstance(item, str) for item in items) else _INVALID


def _boolean_mapping(value: object) -> object:
    if not isinstance(value, Mapping):
        return _INVALID
    return {
        key: item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, bool)
    }


def _put(
    target: dict[str, object],
    source: Mapping[str, object],
    key: str,
    validator: Callable[[object], object],
) -> None:
    if key not in source:
        return
    value = validator(source[key])
    if value is not _INVALID:
        target[key] = value


def _project_sequence(value: object, projector: Callable[[Mapping[str, object]], dict[str, object] | None]) -> object:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return _INVALID
    projected: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        result = projector(item)
        if result is not None:
            projected.append(result)
    return projected


def _project_path(value: object) -> object:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        return _INVALID
    projected: dict[str, object] = {}
    for key in ("objective", "scoring_formula"):
        _put(projected, value, key, _nullable_text)
    for key in ("node_ids", "edge_ids"):
        _put(projected, value, key, _string_list)
    for key in ("distance_km", "risk_cost"):
        _put(projected, value, key, _nullable_number)
    for key in ("estimated_minutes", "visited_node_count"):
        _put(projected, value, key, _nullable_integer)
    return projected


def _project_geo_point(source: Mapping[str, object]) -> dict[str, object] | None:
    longitude = _text(source.get("longitude"))
    latitude = _text(source.get("latitude"))
    if longitude is _INVALID or latitude is _INVALID:
        return None
    projected: dict[str, object] = {
        "longitude": longitude,
        "latitude": latitude,
    }
    _put(projected, source, "node_id", _nullable_text)
    return projected


def _project_real_road_route(value: object) -> object:
    if not isinstance(value, Mapping):
        return _INVALID
    projected: dict[str, object] = {}
    for key in (
        "provider",
        "source",
        "status",
        "coordinate_system",
        "mapping_version",
        "fallback_reason",
    ):
        _put(projected, value, key, _nullable_text)
    for key in ("distance_meters", "duration_seconds"):
        _put(projected, value, key, _nullable_integer)
    for key in ("waypoints", "polyline"):
        _put(
            projected,
            value,
            key,
            lambda item: _project_sequence(item, _project_geo_point),
        )
    return projected


def _project_fleet_score_components(value: object) -> object:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        return _INVALID
    projected: dict[str, object] = {}
    for key in (
        "eta_penalty",
        "distance_penalty",
        "load_penalty",
        "road_risk_penalty",
        "same_station_bonus",
        "cargo_exact_match_bonus",
    ):
        _put(projected, value, key, _nullable_number)
    return projected


def _project_vehicle_candidate(source: Mapping[str, object]) -> dict[str, object] | None:
    vehicle_id = _text(source.get("vehicle_id"))
    if vehicle_id is _INVALID:
        return None
    projected: dict[str, object] = {"vehicle_id": vehicle_id}
    for key in ("driver_id", "vehicle_status", "driver_status", "cargo_capability", "scoring_formula"):
        _put(projected, source, key, _nullable_text)
    for key in (
        "remaining_load_kg",
        "remaining_capacity_kg",
        "gross_weight_tons",
        "pickup_distance_km",
        "score",
    ):
        _put(projected, source, key, _nullable_number)
    _put(projected, source, "pickup_eta_minutes", _nullable_integer)
    _put(projected, source, "eligible", _boolean)
    _put(projected, source, "exclusion_reasons", _string_list)
    _put(projected, source, "pickup_route", _project_path)
    _put(projected, source, "score_components", _project_fleet_score_components)
    return projected


def _project_route_score_components(value: object) -> object:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        return _INVALID
    projected: dict[str, object] = {}
    for key in (
        "normalized_minutes",
        "normalized_distance",
        "normalized_risk",
        "time_penalty",
        "distance_penalty",
        "risk_penalty",
    ):
        _put(projected, value, key, _nullable_number)
    return projected


def _project_route_candidate(source: Mapping[str, object]) -> dict[str, object] | None:
    route_id = _text(source.get("route_id"))
    if route_id is _INVALID:
        return None
    projected: dict[str, object] = {"route_id": route_id}
    for key in (
        "route_name",
        "objective",
        "risk_level",
        "reason",
        "scoring_formula",
        "algorithm_version",
    ):
        _put(projected, source, key, _nullable_text)
    for key in ("distance_km", "risk_cost", "score"):
        _put(projected, source, key, _nullable_number)
    for key in ("estimated_minutes", "visited_node_count", "road_network_version"):
        _put(projected, source, key, _nullable_integer)
    for key in ("node_ids", "edge_ids"):
        _put(projected, source, key, _string_list)
    _put(projected, source, "available", _boolean)
    _put(projected, source, "score_components", _project_route_score_components)
    return projected


def _project_road_node(source: Mapping[str, object]) -> dict[str, object] | None:
    node_id = _text(source.get("node_id"))
    if node_id is _INVALID:
        return None
    projected: dict[str, object] = {"node_id": node_id}
    for key in ("name", "node_type"):
        _put(projected, source, key, _text)
    for key in ("x_km", "y_km"):
        _put(projected, source, key, _number)
    return projected


def _project_road_edge(source: Mapping[str, object]) -> dict[str, object] | None:
    edge_id = _text(source.get("edge_id"))
    if edge_id is _INVALID:
        return None
    projected: dict[str, object] = {"edge_id": edge_id}
    for key in (
        "name",
        "from_node_id",
        "to_node_id",
        "road_level",
        "risk_level",
        "status",
    ):
        _put(projected, source, key, _text)
    for key in ("distance_km", "congestion_factor", "weight_limit_tons"):
        _put(projected, source, key, _number)
    for key in ("base_minutes", "version"):
        _put(projected, source, key, _integer)
    _put(projected, source, "bidirectional", _boolean)
    return projected


def _project_memory_result(source: Mapping[str, object]) -> dict[str, object] | None:
    memory_id = _text(source.get("memory_id"))
    if memory_id is _INVALID:
        return None
    projected: dict[str, object] = {"memory_id": memory_id}
    for key in ("route_id", "historical_resolution"):
        _put(projected, source, key, _nullable_text)
    _put(projected, source, "similarity_score", _nullable_number)
    return projected


def project_intake_event(patch: Mapping[str, object]) -> dict[str, object]:
    projected: dict[str, object] = {}
    for key in (
        "normalized_anomaly",
        "vehicle_id",
        "origin_node_id",
        "destination_node_id",
    ):
        _put(projected, patch, key, _nullable_text)
    _put(projected, patch, "sandtable_context_loaded", _boolean)
    _put(projected, patch, "affected_edge_ids", _string_list)
    return projected


def project_memory_event(patch: Mapping[str, object]) -> dict[str, object]:
    projected: dict[str, object] = {}
    if "memory_results" in patch:
        results = _project_sequence(patch["memory_results"], _project_memory_result)
        if results is not _INVALID:
            projected["memory_results"] = results
    return projected


def project_environment_event(patch: Mapping[str, object]) -> dict[str, object]:
    projected: dict[str, object] = {}
    for key in (
        "weather",
        "road_condition",
        "environment_risk",
        "fallback_reason",
        "environment_provider",
    ):
        _put(projected, patch, key, _nullable_text)
    _put(projected, patch, "fallback_used", _boolean)
    _put(projected, patch, "environment_elapsed_ms", _nullable_number)
    return projected


def project_audit_event(result: object) -> dict[str, object]:
    if not isinstance(result, Mapping):
        return {}
    projected: dict[str, object] = {}
    for key in ("audit_status", "reason"):
        _put(projected, result, key, _nullable_text)
    for key in ("passed", "requires_manual_review"):
        _put(projected, result, key, _boolean)
    for key in ("dispatch_id", "audit_record_id"):
        _put(projected, result, key, _nullable_integer)
    _put(projected, result, "checks", _boolean_mapping)
    return projected


def project_capacity_event(state: Mapping[str, object]) -> dict[str, object]:
    capacity = state.get("capacity_state")
    capacity_state = capacity if isinstance(capacity, Mapping) else {}
    projected: dict[str, object] = {}
    for key in ("vehicle_id", "vehicle_status"):
        if key not in state:
            projected[key] = None
        else:
            _put(projected, state, key, _nullable_text)
    for key, validator in (
        ("driver_available", _boolean),
        ("vehicle_available", _boolean),
        ("capacity_status", _nullable_text),
        ("risk_level", _nullable_text),
        ("reason", _nullable_text),
    ):
        if key not in capacity_state:
            projected[key] = None
        else:
            _put(projected, capacity_state, key, validator)
    if "candidate_vehicles" in state:
        candidates = _project_sequence(state["candidate_vehicles"], _project_vehicle_candidate)
        if candidates is not _INVALID:
            projected["candidate_vehicles"] = candidates
            if candidates:
                formula = _nullable_text(candidates[0].get("scoring_formula"))
                if formula is not _INVALID and formula is not None:
                    projected["scoring_formula"] = formula
    for key in ("selected_vehicle_id", "selected_driver_id"):
        _put(projected, state, key, _nullable_text)
    _put(projected, state, "vehicle_reassigned", _boolean)
    _put(projected, state, "pickup_route", _project_path)
    return projected


def project_routing_event(patch: Mapping[str, object]) -> dict[str, object]:
    projected: dict[str, object] = {}
    for key, validator in (
        ("recommended_route", _nullable_text),
        ("decision", _nullable_text),
        ("decision_reason", _nullable_text),
        ("memory_adopted", _boolean),
        ("requires_manual_review", _boolean),
        ("candidate_routes", lambda value: _project_sequence(value, _project_route_candidate)),
    ):
        if key not in patch:
            projected[key] = None
        else:
            _put(projected, patch, key, validator)
    _put(projected, patch, "adopted_memory_id", _nullable_text)
    _put(projected, patch, "blocked_edge_ids", _string_list)
    _put(projected, patch, "original_path", _project_path)
    _put(projected, patch, "recommended_path", _project_path)
    _put(projected, patch, "real_road_route", _project_real_road_route)
    _put(projected, patch, "distance_delta_km", _nullable_number)
    _put(projected, patch, "eta_delta_minutes", _nullable_integer)
    _put(projected, patch, "routing_status", _nullable_text)
    if "routing_algorithm" in patch:
        value = _nullable_text(patch["routing_algorithm"])
        if value is not _INVALID:
            projected["algorithm"] = value
    _put(projected, patch, "road_network_version", _nullable_integer)
    if "road_network_nodes" in patch:
        value = _project_sequence(patch["road_network_nodes"], _project_road_node)
        if value is not _INVALID:
            projected["network_nodes"] = value
    if "road_network_edges" in patch:
        value = _project_sequence(patch["road_network_edges"], _project_road_edge)
        if value is not _INVALID:
            projected["network_edges"] = value
    recommended = projected.get("recommended_path")
    if isinstance(recommended, Mapping) and "visited_node_count" in recommended:
        projected["visited_node_count"] = recommended["visited_node_count"]
    return projected


def project_dispatch_event(result: object) -> dict[str, object]:
    if not isinstance(result, Mapping):
        return {}
    projected: dict[str, object] = {}
    for key in ("original_vehicle_id", "target_vehicle_id", "target_driver_id", "target_route_id", "status"):
        _put(projected, result, key, _nullable_text)
    _put(projected, result, "version", _nullable_integer)
    _put(projected, result, "executed", _boolean)
    return projected
