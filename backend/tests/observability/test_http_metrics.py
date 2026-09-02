from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry, generate_latest

from app.observability.catalog import build_metric_catalog
from app.observability.http import MetricsMiddleware
from app.observability.recorder import PrometheusMetricsRecorder, SafeMetricsRecorder


def instrumented_app() -> tuple[FastAPI, CollectorRegistry]:
    registry = CollectorRegistry()
    recorder = SafeMetricsRecorder(PrometheusMetricsRecorder(build_metric_catalog(registry)))
    app = FastAPI()
    app.add_middleware(MetricsMiddleware, recorder=recorder)

    @app.get("/items/{item_id}")
    def item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    @app.get("/conflict")
    def conflict() -> None:
        raise HTTPException(status_code=409, detail="expected")

    @app.get("/explode")
    def explode() -> None:
        raise RuntimeError("boom")

    return app, registry


def test_http_metrics_recorded() -> None:
    app, registry = instrumented_app()

    response = TestClient(app).get("/items/abc")

    assert response.json() == {"item_id": "abc"}
    text = generate_latest(registry).decode()
    assert 'countyflow_http_requests_total{method="GET",route_template="/items/{item_id}",status_class="2xx"} 1.0' in text
    assert 'countyflow_http_inflight_requests 0.0' in text


def test_http_metrics_use_route_template() -> None:
    app, registry = instrumented_app()

    TestClient(app).get("/items/secret-id")

    text = generate_latest(registry).decode()
    assert 'route_template="/items/{item_id}"' in text
    assert "secret-id" not in text


def test_http_metrics_classify_404_409_and_500_without_swallowing() -> None:
    app, registry = instrumented_app()
    client = TestClient(app, raise_server_exceptions=False)

    assert client.get("/missing/value").status_code == 404
    assert client.get("/conflict").status_code == 409
    assert client.get("/explode").status_code == 500

    text = generate_latest(registry).decode()
    assert 'route_template="unmatched",status_class="4xx"' in text
    assert 'route_template="/conflict",status_class="4xx"' in text
    assert 'route_template="/explode",status_class="5xx"' in text
    assert 'countyflow_http_inflight_requests 0.0' in text
