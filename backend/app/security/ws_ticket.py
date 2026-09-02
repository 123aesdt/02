import hashlib
import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.security.models import AuthenticatedPrincipal
from app.security.permissions import Permission

TICKET_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


class WsTicketUnavailable(Exception):
    """Raised when ticket security state cannot be stored or consumed."""


class WsTicketRejected(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class IssuedWsTicket:
    ticket: str = field(repr=False)
    target_type: str
    target_id: str
    expires_at: datetime


@dataclass(frozen=True)
class ConsumedWsTicket:
    subject_id: str
    target_type: str
    target_id: str
    required_permission: Permission
    issued_at: datetime
    expires_at: datetime


class RedisWsTicketService:
    def __init__(
        self,
        redis,
        *,
        namespace: str = "countyflow:auth:ws-ticket",
        ttl_seconds: int = 45,
        clock=None,
    ) -> None:
        normalized = namespace.strip().strip(":")
        if not normalized:
            raise ValueError("WebSocket ticket namespace must not be empty")
        if not 15 <= ttl_seconds <= 120:
            raise ValueError("WebSocket ticket TTL must be between 15 and 120 seconds")
        self._redis = redis
        self._namespace = normalized
        self._ttl_seconds = ttl_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

    async def issue(
        self,
        principal: AuthenticatedPrincipal,
        *,
        target_type: str,
        target_id: str,
        required_permission: Permission,
    ) -> IssuedWsTicket:
        if not principal.can(required_permission):
            raise WsTicketRejected("WS_TICKET_PERMISSION_DENIED")
        normalized_type = self._text(target_type, "target_type", 32)
        normalized_id = self._text(target_id, "target_id", 128)
        issued_at = self._clock()
        expires_at = issued_at + timedelta(seconds=self._ttl_seconds)
        serialized = json.dumps(
            {
                "subject_id": principal.subject_id,
                "target_type": normalized_type,
                "target_id": normalized_id,
                "required_permission": required_permission.value,
                "issued_at": issued_at.isoformat(),
                "expires_at": expires_at.isoformat(),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        for _ in range(3):
            ticket = secrets.token_urlsafe(32)
            try:
                stored = await self._redis.set(
                    self._key(ticket),
                    serialized,
                    ex=self._ttl_seconds,
                    nx=True,
                )
            except Exception as error:
                raise WsTicketUnavailable from error
            if stored:
                return IssuedWsTicket(ticket, normalized_type, normalized_id, expires_at)
        raise WsTicketUnavailable

    async def consume(
        self,
        ticket: str,
        *,
        target_type: str,
        target_id: str,
        required_permission: Permission,
    ) -> ConsumedWsTicket:
        if not TICKET_PATTERN.fullmatch(ticket):
            raise WsTicketRejected("WS_TICKET_INVALID")
        try:
            serialized = await self._redis.getdel(self._key(ticket))
        except Exception as error:
            raise WsTicketUnavailable from error
        if serialized is None:
            raise WsTicketRejected("WS_TICKET_REPLAYED_OR_EXPIRED")
        try:
            if isinstance(serialized, bytes):
                serialized = serialized.decode("utf-8")
            payload = json.loads(serialized)
            consumed = ConsumedWsTicket(
                subject_id=self._text(payload["subject_id"], "subject_id", 128),
                target_type=self._text(payload["target_type"], "target_type", 32),
                target_id=self._text(payload["target_id"], "target_id", 128),
                required_permission=Permission(payload["required_permission"]),
                issued_at=datetime.fromisoformat(payload["issued_at"]),
                expires_at=datetime.fromisoformat(payload["expires_at"]),
            )
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            raise WsTicketRejected("WS_TICKET_INVALID") from None
        if consumed.expires_at <= self._clock():
            raise WsTicketRejected("WS_TICKET_REPLAYED_OR_EXPIRED")
        if consumed.target_type != target_type or consumed.target_id != target_id:
            raise WsTicketRejected("WS_TICKET_WRONG_SCOPE")
        if consumed.required_permission is not required_permission:
            raise WsTicketRejected("WS_TICKET_PERMISSION_DENIED")
        return consumed

    def _key(self, ticket: str) -> str:
        digest = hashlib.sha256(ticket.encode("ascii")).hexdigest()
        return f"{self._namespace}:{digest}"

    @staticmethod
    def _text(value: object, name: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
            raise ValueError(f"invalid WebSocket ticket {name}")
        return value.strip()
