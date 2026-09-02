from prometheus_client import CollectorRegistry, generate_latest

from app.observability.catalog import build_metric_catalog
from app.observability.recorder import MetricLabelError, NoOpMetricsRecorder, PrometheusMetricsRecorder, SafeMetricsRecorder


def test_agent_recorder_rejects_unknown_label_value() -> None:
    recorder = PrometheusMetricsRecorder(build_metric_catalog(CollectorRegistry()))

    try:
        recorder.observe_agent("unknown-agent", "success", 0.01)
    except MetricLabelError as error:
        assert "agent" in str(error)
    else:
        raise AssertionError("unknown agent label must be rejected")


def test_metrics_failure_does_not_fail_business() -> None:
    class ThrowingRecorder(NoOpMetricsRecorder):
        def observe_agent(self, agent: str, result: str, seconds: float) -> None:
            raise RuntimeError("instrumentation failed")

    recorder = SafeMetricsRecorder(ThrowingRecorder())
    business_result = {"decision": "REROUTE"}

    recorder.observe_agent("routing", "success", 0.01)

    assert business_result == {"decision": "REROUTE"}


def test_prometheus_recorder_records_known_agent() -> None:
    registry = CollectorRegistry()
    recorder = PrometheusMetricsRecorder(build_metric_catalog(registry))

    recorder.observe_agent("routing", "success", 0.25)

    text = generate_latest(registry).decode()
    assert 'countyflow_agent_executions_total{agent="routing",result="success"} 1.0' in text
    assert 'countyflow_agent_duration_seconds_count{agent="routing"} 1.0' in text
