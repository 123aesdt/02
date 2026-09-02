"""Run destructive-but-cleaned-up reliability probes against the Docker runtime."""

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from uuid import uuid4

from app.core.database import build_session_factory
from app.models.dispatch import Dispatch
from app.models.order import Order
from app.streams.models import DeadLetterMessage, DispatchTaskMessage
from app.streams.redis_queue import RedisStreamQueue
from app.streams.retry import RetryPolicy
from app.workers.dispatch_worker import DispatchWorker
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError


class FailingGraph:
    async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("controlled real-Redis DLQ probe")


async def no_sleep(_: float) -> None:
    return None


def verify_mysql_optimistic_lock() -> dict[str, object]:
    factory = build_session_factory(os.environ["DATABASE_URL"])
    marker = uuid4().hex
    with factory() as seed:
        order_id = seed.scalar(select(Order.id).order_by(Order.id).limit(1))
        if order_id is None:
            raise RuntimeError("Docker seed order is missing.")
        dispatch = Dispatch(
            dispatch_no=f"DSP-LOCK-{marker}",
            order_id=order_id,
            target_route_id="lock-original",
            status="PROPOSED",
        )
        seed.add(dispatch)
        seed.commit()
        dispatch_id = dispatch.id
        initial_version = dispatch.version

    session_a = factory()
    session_b = factory()
    try:
        dispatch_a = session_a.get(Dispatch, dispatch_id)
        dispatch_b = session_b.get(Dispatch, dispatch_id)
        if dispatch_a is None or dispatch_b is None:
            raise RuntimeError("Optimistic-lock probe row disappeared.")
        dispatch_a.target_route_id = "lock-session-a"
        session_a.commit()
        committed_version = dispatch_a.version
        dispatch_b.target_route_id = "lock-session-b"
        try:
            session_b.commit()
        except StaleDataError:
            session_b.rollback()
            conflict = "StaleDataError"
        else:
            raise RuntimeError("Second MySQL session overwrote a stale Dispatch version.")
    finally:
        session_a.close()
        session_b.close()

    with factory() as verify:
        persisted = verify.get(Dispatch, dispatch_id)
        if persisted is None or persisted.target_route_id != "lock-session-a":
            raise RuntimeError("MySQL optimistic-lock winner was overwritten.")
        verify.delete(persisted)
        verify.commit()

    return {
        "database": "mysql",
        "initial_version": initial_version,
        "committed_version": committed_version,
        "second_commit": conflict,
        "winner": "lock-session-a",
        "probe_row_cleaned": True,
    }


async def verify_redis_dlq() -> dict[str, object]:
    suffix = uuid4().hex
    stream = f"countyflow:phase5a:dlq:{suffix}"
    dlq_stream = f"{stream}:dead"
    group = f"phase5a-{suffix}"
    client = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6380/0"), decode_responses=False)
    queue = RedisStreamQueue(client, stream, group, "worker-1", dlq_stream_name=dlq_stream)
    task = DispatchTaskMessage(
        schema_version="1",
        task_id=f"TASK-DLQ-{suffix[:16]}",
        order_id=1,
        anomaly_id=1,
        idempotency_key=f"phase5a-dlq-{suffix}",
        created_at=datetime.now(UTC).isoformat(),
        payload={
            "driver_id": "driver-li",
            "vehicle_id": "vehicle-001",
            "route_id": "xinping-road",
            "anomaly_type": "rain_slippery",
            "anomaly_description": "controlled DLQ integration probe",
        },
    )
    worker = DispatchWorker(
        queue,
        FailingGraph(),
        read_count=1,
        block_ms=1,
        pending_min_idle_ms=0,
        recovery_count=1,
        retry_policy=RetryPolicy(max_delivery_attempts=3, base_delay_ms=0, max_delay_ms=0),
        sleep_func=no_sleep,
    )
    try:
        await queue.ensure_consumer_group()
        original_id = await queue.publish(task)
        first = await worker.run_once()
        if len(first) != 1 or first[0].acknowledged:
            raise RuntimeError("Controlled Redis failure did not remain pending.")
        retry = await worker.recover_once()
        if len(retry) != 1 or not retry[0].retried or retry[0].delivery_count != 2:
            raise RuntimeError("Real Redis retry delivery count was not 2.")
        dlq = await worker.recover_once()
        if len(dlq) != 1 or not dlq[0].moved_to_dlq or dlq[0].delivery_count != 3:
            raise RuntimeError("Real Redis message did not move to DLQ at the configured limit.")
        pending = await client.xpending(stream, group)
        entries = await client.xrange(dlq_stream)
        if len(entries) != 1:
            raise RuntimeError("Real Redis DLQ does not contain exactly one probe message.")
        dead_letter = DeadLetterMessage.from_json(entries[0][1][b"data"])
        if (
            dead_letter.original_message_id != original_id
            or dead_letter.task_id != task.task_id
            or dead_letter.idempotency_key != task.idempotency_key
        ):
            raise RuntimeError("Real Redis DLQ did not preserve message/task identity.")
        return {
            "redis": "server",
            "original_message_id": original_id,
            "task_id": dead_letter.task_id,
            "delivery_count": dead_letter.delivery_count,
            "dlq_message_id": entries[0][0].decode() if isinstance(entries[0][0], bytes) else entries[0][0],
            "pending_after_dlq": pending["pending"],
            "original_acked": pending["pending"] == 0,
            "identity_preserved": True,
        }
    finally:
        await client.delete(stream, dlq_stream)
        await client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=("mysql-lock", "redis-dlq"))
    args = parser.parse_args()
    result = verify_mysql_optimistic_lock() if args.scenario == "mysql-lock" else asyncio.run(verify_redis_dlq())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
