from datetime import UTC, datetime, timedelta

import pytest
from security_support import principal_for

from app.security.permissions import Permission
from app.security.ws_ticket import RedisWsTicketService, WsTicketRejected


class TicketRedis:
    def __init__(self) -> None:
        self.values = {}
        self.set_calls = []

    async def set(self, key, value, *, ex, nx):
        self.set_calls.append((key, value, ex, nx))
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def getdel(self, key):
        return self.values.pop(key, None)


@pytest.mark.asyncio
async def test_ws_ticket_single_use() -> None:
    redis = TicketRedis()
    service = RedisWsTicketService(redis)
    issued = await service.issue(
        principal_for(),
        target_type="task",
        target_id="TASK-1",
        required_permission=Permission.DISPATCH_READ,
    )

    consumed = await service.consume(
        issued.ticket,
        target_type="task",
        target_id="TASK-1",
        required_permission=Permission.DISPATCH_READ,
    )

    assert consumed.subject_id == "test-admin"
    with pytest.raises(WsTicketRejected, match="WS_TICKET_REPLAYED_OR_EXPIRED"):
        await service.consume(
            issued.ticket,
            target_type="task",
            target_id="TASK-1",
            required_permission=Permission.DISPATCH_READ,
        )


@pytest.mark.asyncio
async def test_ws_ticket_wrong_scope() -> None:
    redis = TicketRedis()
    service = RedisWsTicketService(redis)
    issued = await service.issue(
        principal_for(),
        target_type="task",
        target_id="TASK-A",
        required_permission=Permission.DISPATCH_READ,
    )

    with pytest.raises(WsTicketRejected, match="WS_TICKET_WRONG_SCOPE"):
        await service.consume(
            issued.ticket,
            target_type="task",
            target_id="TASK-B",
            required_permission=Permission.DISPATCH_READ,
        )


@pytest.mark.asyncio
async def test_ws_ticket_expired() -> None:
    redis = TicketRedis()
    now = datetime(2026, 8, 28, tzinfo=UTC)
    service = RedisWsTicketService(redis, clock=lambda: now)
    issued = await service.issue(
        principal_for(),
        target_type="task",
        target_id="TASK-1",
        required_permission=Permission.DISPATCH_READ,
    )
    service._clock = lambda: now + timedelta(seconds=46)

    with pytest.raises(WsTicketRejected, match="WS_TICKET_REPLAYED_OR_EXPIRED"):
        await service.consume(
            issued.ticket,
            target_type="task",
            target_id="TASK-1",
            required_permission=Permission.DISPATCH_READ,
        )


@pytest.mark.asyncio
async def test_ws_ticket_stores_digest_not_ticket() -> None:
    redis = TicketRedis()
    service = RedisWsTicketService(redis)
    issued = await service.issue(
        principal_for(),
        target_type="task",
        target_id="TASK-1",
        required_permission=Permission.DISPATCH_READ,
    )

    key, serialized, ttl, only_if_missing = redis.set_calls[0]
    assert len(issued.ticket) >= 43
    assert issued.ticket not in key
    assert issued.ticket not in serialized
    assert key.startswith("countyflow:auth:ws-ticket:")
    assert ttl == 45
    assert only_if_missing is True
    assert issued.ticket not in repr(issued)
