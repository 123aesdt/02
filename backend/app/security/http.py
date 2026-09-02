import fnmatch
import json
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        runtime_profile: str,
        hsts_enabled: bool,
        oidc_issuer: str,
    ) -> None:
        self.app = app
        self._runtime_profile = runtime_profile
        self._hsts_enabled = hsts_enabled
        self._csp = self._content_security_policy(runtime_profile, oidc_issuer)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def add_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                values = {
                    b"x-content-type-options": b"nosniff",
                    b"referrer-policy": b"strict-origin-when-cross-origin",
                    b"permissions-policy": b"camera=(), microphone=(), geolocation=(), payment=(), usb=()",
                    b"content-security-policy": self._csp.encode("ascii"),
                }
                if self._runtime_profile == "production" and self._hsts_enabled and scope.get("scheme") == "https":
                    values[b"strict-transport-security"] = b"max-age=31536000; includeSubDomains"
                headers = [(key, value) for key, value in message.get("headers", []) if key.lower() not in values]
                headers.extend(values.items())
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, add_headers)

    @staticmethod
    def _content_security_policy(runtime_profile: str, oidc_issuer: str) -> str:
        connect_sources = ["'self'"]
        if runtime_profile != "production":
            connect_sources.extend(
                [
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",
                    "http://localhost:8001",
                    "ws://localhost:5173",
                    "ws://127.0.0.1:5173",
                    "ws://localhost:8001",
                ]
            )
        elif oidc_issuer:
            parsed = urlsplit(oidc_issuer)
            if parsed.scheme == "https" and parsed.netloc:
                connect_sources.append(f"https://{parsed.netloc}")
        directives = [
            "default-src 'self'",
            "base-uri 'self'",
            "object-src 'none'",
            "frame-ancestors 'none'",
            "form-action 'self'",
            "img-src 'self' data:",
            "font-src 'self' data:",
            "style-src 'self' 'unsafe-inline'",
            "script-src 'self'",
            f"connect-src {' '.join(connect_sources)}",
        ]
        return "; ".join(directives)


class JsonBodyLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        default_limit_bytes: int,
        route_limits: dict[tuple[str, str], int],
    ) -> None:
        if default_limit_bytes <= 0 or any(limit <= 0 for limit in route_limits.values()):
            raise ValueError("request body limits must be positive")
        self.app = app
        self._default_limit = default_limit_bytes
        self._route_limits = dict(route_limits)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_type = headers.get(b"content-type", b"").decode("latin-1").lower()
        if "json" not in content_type:
            await self.app(scope, receive, send)
            return
        limit = self._limit(scope["method"], scope.get("path", ""))
        raw_length = headers.get(b"content-length")
        if raw_length is not None:
            try:
                if int(raw_length) > limit:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                pass
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            body.extend(message.get("body", b""))
            if len(body) > limit:
                await self._reject(scope, receive, send)
                return
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if delivered:
                return {"type": "http.request", "body": b"", "more_body": False}
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)

    def _limit(self, method: str, path: str) -> int:
        for (rule_method, pattern), limit in self._route_limits.items():
            if method == rule_method and fnmatch.fnmatchcase(path, pattern):
                return limit
        return self._default_limit

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        body = json.dumps(
            {"code": "PAYLOAD_TOO_LARGE", "message": "The request payload is too large."},
            separators=(",", ":"),
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("ascii"))],
            }
        )
        await send({"type": "http.response.body", "body": body})
