import json
from datetime import UTC, datetime

import pytest

from app.agents.intake import intake_node
from app.graph.builder import build_graph


def valid_state(description="  李师傅在雨天经过新平路，道路出现湿滑风险。  "):
    return {"task_id": "t", "order_id": 1, "driver_id": "d", "route_id": "r", "anomaly_type": "risk", "anomaly_description": description}


def test_intake_normalizes_anomaly_and_preserves_context():
    state = valid_state()
    patch = intake_node(state)
    assert patch["normalized_anomaly"] == "李师傅在雨天经过新平路，道路出现湿滑风险。"
    assert datetime.fromisoformat(patch["started_at"]).tzinfo is UTC
    assert state["task_id"] == "t"


def test_intake_started_at_is_json_serializable_utc_timestamp():
    patch = intake_node(valid_state())

    json.dumps(patch)
    assert datetime.fromisoformat(patch["started_at"]).tzinfo is UTC


def test_intake_invalid_input_requires_manual_review():
    patch = intake_node(valid_state("   "))
    assert patch["requires_manual_review"] is True
    assert patch["error_code"] == "INTAKE_VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_graph_runs_intake_node():
    result = await build_graph().ainvoke(valid_state())
    assert result["normalized_anomaly"] == "李师傅在雨天经过新平路，道路出现湿滑风险。"
