import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest
from scripts import offline_fleet_routing_acceptance as acceptance
from scripts.offline_fleet_routing_acceptance import _submit_and_wait, _verify_candidate_explainability

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class _PublicApiClient:
    def __init__(self) -> None:
        self.submitted: dict[str, Any] | None = None

    async def post(self, path: str, *, json: dict[str, Any]) -> httpx.Response:
        assert path == "/api/v1/dispatch-tasks"
        self.submitted = json
        return httpx.Response(202, json={"task_id": "task-test"}, request=httpx.Request("POST", path))

    async def get(self, path: str) -> httpx.Response:
        payload = {"ready": True} if path == "/api/v1/dispatch-tasks/task-test" else {"task_id": "task-test"}
        return httpx.Response(200, json=payload, request=httpx.Request("GET", path))


@pytest.mark.parametrize(
    ("order", "driver_id", "route_id"),
    [
        (
            {"row_id": 1, "order_no": "DEMO-ORDER-001", "driver_id": None, "vehicle_id": "V-001", "route_id": None},
            "D-001",
            "xinping-road",
        ),
        (
            {"row_id": 5, "order_no": "DEMO-ORDER-005", "driver_id": None, "vehicle_id": "V-008", "route_id": None},
            "D-007",
            "xinping-road",
        ),
    ],
)
def test_submit_uses_explicit_sandtable_context_when_public_order_relations_are_null(
    order: dict[str, Any],
    driver_id: str,
    route_id: str,
) -> None:
    client = _PublicApiClient()

    asyncio.run(
        _submit_and_wait(
            client,  # type: ignore[arg-type]
            order=order,
            driver_id=driver_id,
            route_id=route_id,
            anomaly_type="VEHICLE_BREAKDOWN",
            description="验收输入",
            vehicle_status="BROKEN",
            idempotency_key="acceptance-contract-test",
            timeout_seconds=1,
        )
    )

    assert client.submitted is not None
    assert client.submitted["driver_id"] == driver_id
    assert client.submitted["route_id"] == route_id


def test_real_acceptance_identifies_the_breakdown_incident_node(monkeypatch: pytest.MonkeyPatch) -> None:
    submissions: list[dict[str, Any]] = []

    class _ContextClient:
        def __init__(self, **_: Any) -> None:
            pass

        async def __aenter__(self) -> "_ContextClient":
            return self

        async def __aexit__(self, *_: Any) -> None:
            pass

    async def resolve_order(_: Any, order_no: str) -> dict[str, Any]:
        vehicle_id = "V-001" if order_no == "DEMO-ORDER-001" else "V-008"
        return {"row_id": 1, "order_no": order_no, "vehicle_id": vehicle_id}

    async def submit_and_wait(_: Any, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        submissions.append(kwargs)
        task_id = f"task-{len(submissions)}"
        return task_id, {"task_id": task_id}

    monkeypatch.setenv("E2E_ACCESS_TOKEN", "test-token")
    monkeypatch.setattr(acceptance.httpx, "AsyncClient", _ContextClient)
    monkeypatch.setattr(acceptance, "_resolve_order", resolve_order)
    monkeypatch.setattr(acceptance, "_submit_and_wait", submit_and_wait)
    monkeypatch.setattr(acceptance, "_verify_breakdown", lambda result: result)
    monkeypatch.setattr(acceptance, "_verify_blocked", lambda result: result)

    asyncio.run(acceptance.run("http://test", 1))
    asyncio.run(acceptance.run("http://test", 1))

    assert "新平路 K3.2" in submissions[0]["description"]
    assert len({item["idempotency_key"] for item in submissions}) == 4


def test_docker_acceptance_resets_mutable_virtual_scenario_state() -> None:
    source = (PROJECT_ROOT / "scripts" / "test-offline-fleet-routing.ps1").read_text(encoding="utf-8")

    assert "UPDATE fleet_vehicles SET status='AVAILABLE', version=version+1" in source
    assert "WHERE vehicle_id='V-005' AND status<>'AVAILABLE'" in source
    assert "UPDATE road_edges SET status='OPEN', congestion_factor=1.00, version=version+1" in source
    assert "WHERE edge_id='E04' AND (status<>'OPEN' OR congestion_factor<>1.00)" in source
    assert source.index("Invoke-MySqlCommand") < source.index("$env:E2E_ACCESS_TOKEN")
    assert "-e $Query 2>&1)" in source
    assert source.count("$nativeErrorPreference = $ErrorActionPreference") == 2
    assert source.count("$ErrorActionPreference = 'Continue'") == 2
    assert source.count("$ErrorActionPreference = $nativeErrorPreference") == 2


def test_compacted_rejected_candidate_keeps_an_explainable_exclusion() -> None:
    _verify_candidate_explainability(
        {
            "vehicle_id": "V-001",
            "eligible": None,
            "exclusion_reasons": ["ORIGINAL_VEHICLE_EXCLUDED", "VEHICLE_UNAVAILABLE"],
        },
        selected_vehicle_id="V-005",
    )
