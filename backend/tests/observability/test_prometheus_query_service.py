import pytest

from app.observability.query_catalog import ObservabilityQueryKey, UnknownObservabilityQuery, resolve_query


def test_prometheus_query_allowlist() -> None:
    assert "countyflow:slo:http_qps_5m" in resolve_query(ObservabilityQueryKey.HTTP_QPS, "5m")
    with pytest.raises(UnknownObservabilityQuery):
        resolve_query("rate(secret_metric[5m])", "5m")
