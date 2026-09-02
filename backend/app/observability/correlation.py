"""ASGI request correlation without payload mutation."""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability.context import bind_observability_context, normalize_correlation_id


class CorrelationMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw = headers.get(b"x-request-id")
        correlation_id = normalize_correlation_id(raw.decode("ascii", errors="ignore") if raw else None)

        async def add_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", correlation_id.encode("ascii")))
                message = {**message, "headers": response_headers}
            await send(message)

        with bind_observability_context(correlation_id=correlation_id):
            await self.app(scope, receive, add_header)
