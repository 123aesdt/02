def build_dispatch_payload(unique_token: str) -> dict[str, object]:
    if not unique_token.strip():
        raise ValueError("Load-test unique token is required.")
    return {
        "order_id": 1,
        "anomaly_id": 1,
        "driver_id": "driver-li",
        "vehicle_id": "vehicle-001",
        "route_id": "xinping-road",
        "anomaly_type": "rain_slippery",
        "anomaly_description": "Phase 5B HTTP acceptance workload",
        "idempotency_key": f"phase5b-load-{unique_token}",
    }
