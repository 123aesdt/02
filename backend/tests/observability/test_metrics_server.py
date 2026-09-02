from prometheus_client import CollectorRegistry

from app.observability.runtime import build_metrics_runtime


class FakeServer:
    def __init__(self) -> None:
        self.shutdown_calls = 0
        self.close_calls = 0

    def shutdown(self) -> None:
        self.shutdown_calls += 1

    def server_close(self) -> None:
        self.close_calls += 1


class FakeThread:
    def __init__(self) -> None:
        self.join_calls = 0

    def join(self, timeout: float | None = None) -> None:
        self.join_calls += 1


def test_metrics_runtime_starts_once_and_stops_cleanly() -> None:
    calls: list[tuple[int, str, CollectorRegistry]] = []
    server = FakeServer()
    thread = FakeThread()

    def factory(port: int, addr: str, registry: CollectorRegistry):
        calls.append((port, addr, registry))
        return server, thread

    registry = CollectorRegistry()
    runtime = build_metrics_runtime(True, "0.0.0.0", 9100, registry=registry, server_factory=factory)

    runtime.start()
    runtime.start()
    runtime.stop()
    runtime.stop()

    assert calls == [(9100, "0.0.0.0", registry)]
    assert (server.shutdown_calls, server.close_calls, thread.join_calls) == (1, 1, 1)


def test_disabled_metrics_runtime_does_not_bind_network() -> None:
    def forbidden_factory(*args, **kwargs):
        raise AssertionError("disabled runtime must not start a server")

    runtime = build_metrics_runtime(False, "0.0.0.0", 9100, server_factory=forbidden_factory)

    runtime.start()
    runtime.stop()
