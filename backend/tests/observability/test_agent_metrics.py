import pytest
from prometheus_client import CollectorRegistry, generate_latest

from app.graph.builder import _instrument_node
from app.observability.catalog import build_metric_catalog
from app.observability.recorder import PrometheusMetricsRecorder, SafeMetricsRecorder


def recorder_and_registry():
    registry = CollectorRegistry()
    return SafeMetricsRecorder(PrometheusMetricsRecorder(build_metric_catalog(registry))), registry


@pytest.mark.asyncio
async def test_agent_metrics_known_labels() -> None:
    recorder, registry = recorder_and_registry()

    for agent in ("intake", "entity_memory", "graph_memory", "environment", "capacity", "routing", "dispatch", "audit"):
        wrapped = _instrument_node(agent, lambda state: {}, recorder)
        await wrapped({})

    text = generate_latest(registry).decode()
    for agent in ("intake", "entity_memory", "graph_memory", "environment", "capacity", "routing", "dispatch", "audit"):
        assert f'countyflow_agent_executions_total{{agent="{agent}",result="success"}} 1.0' in text
    assert "task_id=" not in text


@pytest.mark.asyncio
async def test_agent_duration_histogram() -> None:
    recorder, registry = recorder_and_registry()

    await _instrument_node("routing", lambda state: {"decision": "REROUTE"}, recorder)({})

    assert 'countyflow_agent_duration_seconds_count{agent="routing"} 1.0' in generate_latest(registry).decode()


@pytest.mark.asyncio
async def test_agent_inflight_returns_to_zero_after_error() -> None:
    recorder, registry = recorder_and_registry()

    def fail(state):
        raise RuntimeError("business failure")

    with pytest.raises(RuntimeError, match="business failure"):
        await _instrument_node("routing", fail, recorder)({})

    text = generate_latest(registry).decode()
    assert 'countyflow_agent_inflight{agent="routing"} 0.0' in text
    assert 'countyflow_agent_executions_total{agent="routing",result="error"} 1.0' in text
