# CountyFlow authenticated HTTP load workload

The Locust workload targets the real Docker backend at `http://localhost:8001`. It measures HTTP submission and query latency only; asynchronous Agent terminal latency is intentionally excluded.

Set `PYTHONPATH=backend`, `LOCUST_TASK_ID`, `RUNTIME_PROFILE=docker-dev`, and the ignored local development JWT settings. The mix remains 50% health, 30% task status, 19% task result, and 1% unique dispatch submission. Each virtual user receives a unique short-lived Dispatcher principal so the real per-principal token bucket stays enabled without changing production policy. Every POST uses a unique idempotency key and the idempotent Docker seed order/anomaly.

Run the formal V2-G2 benchmark with `powershell -ExecutionPolicy Bypass -File scripts/test-security-performance.ps1`. The JSON evidence contains only safe profile metadata and aggregate results; tokens and signing secrets are never serialized.
