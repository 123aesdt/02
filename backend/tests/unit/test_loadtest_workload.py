from app.acceptance.loadtest import build_dispatch_payload


def test_loadtest_dispatch_payloads_are_valid_and_idempotently_unique():
    first = build_dispatch_payload("worker-a-1")
    second = build_dispatch_payload("worker-a-2")

    assert first == {
        "order_id": 1,
        "anomaly_id": 1,
        "driver_id": "driver-li",
        "vehicle_id": "vehicle-001",
        "route_id": "xinping-road",
        "anomaly_type": "rain_slippery",
        "anomaly_description": "Phase 5B HTTP acceptance workload",
        "idempotency_key": "phase5b-load-worker-a-1",
    }
    assert second["idempotency_key"] == "phase5b-load-worker-a-2"
    assert first["idempotency_key"] != second["idempotency_key"]
