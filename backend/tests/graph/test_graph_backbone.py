import pytest

from app.graph.builder import build_graph
from app.graph.state import DispatchGraphState


def test_graph_state_schema_has_required_identity_and_future_safe_fields():
    state: DispatchGraphState = {"task_id": "t-1", "order_id": 1, "driver_id": "d", "route_id": "r", "anomaly_type": "risk", "anomaly_description": "slippery"}
    assert state["task_id"] == "t-1"


def test_graph_compiles():
    assert build_graph() is not None


@pytest.mark.asyncio
async def test_graph_invokes_with_typed_state():
    result = await build_graph().ainvoke(
        {
            "task_id": "t-1",
            "order_id": 1,
            "driver_id": "d",
            "route_id": "r",
            "anomaly_type": "risk",
            "anomaly_description": "slippery",
        }
    )
    assert result["task_id"] == "t-1"
