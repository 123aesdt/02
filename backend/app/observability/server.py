"""Explicitly owned Prometheus HTTP server lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from threading import RLock
from typing import Protocol

from prometheus_client import CollectorRegistry, start_http_server


class ServerHandle(Protocol):
    def shutdown(self) -> None: ...
    def server_close(self) -> None: ...


class ThreadHandle(Protocol):
    def join(self, timeout: float | None = None) -> None: ...


ServerFactory = Callable[[int, str, CollectorRegistry], tuple[ServerHandle, ThreadHandle]]


def _start_server(port: int, addr: str, registry: CollectorRegistry) -> tuple[ServerHandle, ThreadHandle]:
    return start_http_server(port, addr=addr, registry=registry)


class MetricsRuntime:
    def __init__(self, enabled: bool, host: str, port: int, registry: CollectorRegistry, server_factory: ServerFactory = _start_server) -> None:
        self.enabled = enabled
        self.host = host
        self.port = port
        self.registry = registry
        self._server_factory = server_factory
        self._handles: tuple[ServerHandle, ThreadHandle] | None = None
        self._lock = RLock()

    def start(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            if self._handles is None:
                self._handles = self._server_factory(self.port, self.host, self.registry)

    def stop(self) -> None:
        with self._lock:
            handles, self._handles = self._handles, None
        if handles is None:
            return
        server, thread = handles
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
