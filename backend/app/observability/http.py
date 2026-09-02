"""ASGI HTTP metrics that preserve route and response semantics."""

from __future__ import annotations

from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability.recorder import MetricsRecorder


def route_template_from_scope(scope: Scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) and path.startswith("/") else "unmatched"


def normalized_method(value: str) -> str:
    method = value.upper()
    return method if method in {"GET", "POST", "OPTIONS"} else "OTHER"


class MetricsMiddleware:
    def __init__(self, app: ASGIApp, recorder: MetricsRecorder) -> None:
        self.app = app
        self.recorder = recorder

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = perf_counter()
        status_code = 500
        self.recorder.adjust_gauge("countyflow_http_inflight_requests", 1)

        async def capture_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            method = normalized_method(str(scope.get("method", "OTHER")))
            route_template = route_template_from_scope(scope)
            status_class = f"{min(max(status_code // 100, 2), 5)}xx"
            labels = {"method": method, "route_template": route_template}
            self.recorder.increment("countyflow_http_requests_total", {**labels, "status_class": status_class})
            self.recorder.observe("countyflow_http_request_duration_seconds", perf_counter() - started, labels)
            self.recorder.adjust_gauge("countyflow_http_inflight_requests", -1)
