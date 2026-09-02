"""Exercise V2-D1 against real MySQL and the official Redis checkpoint saver."""

import argparse
import asyncio
import json
import statistics
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NotRequired, TypedDict
from uuid import uuid4

from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langgraph.graph import END, START, StateGraph
from redis.asyncio import Redis

from app.core.database import build_session_factory
from app.idempotency.service import IdempotencyService
from app.models.order import Order
from app.models.runtime_override import RuntimeOverride, RuntimeOverrideAttempt
from app.models.runtime_thread import RuntimeThread
from app.runtime_overrides.checkpoint_updater import LangGraphStateUpdater
from app.runtime_overrides.models import RuntimeOverrideRequest, RuntimeOverrideStatus
from app.runtime_overrides.policy import RuntimeOverridePolicy
from app.runtime_overrides.redis_lock import RuntimeBoundaryLock
from app.runtime_overrides.service import RuntimeOverrideService
from app.runtime_overrides.sqlalchemy_repository import (
    SqlAlchemyRuntimeOverrideRepository,
)
from app.runtime_threads.checkpoint_store import RedisRuntimeCheckpointStore
from app.runtime_threads.models import BoundaryClaimConflict
from app.runtime_threads.sqlalchemy_repository import SqlAlchemyRuntimeThreadRepository
from app.security.models import AuthenticatedPrincipal, AuthMethod
from app.security.permissions import ROLE_PERMISSION_MATRIX, Role


class State(TypedDict):
    vehicle_id: str
    vehicle_status: str
    last_completed_node: NotRequired[str]
    completed_node_count: NotRequired[int]
    capacity_observed_status: NotRequired[str]


def summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    p95 = max(0, (95 * len(ordered) + 99) // 100 - 1)
    return {
        "minimum": round(ordered[0], 3),
        "average": round(statistics.fmean(ordered), 3),
        "p95": round(ordered[p95], 3),
        "p99_or_maximum": round(ordered[-1], 3),
    }


def build_override_graph(saver: AsyncRedisSaver):
    def environment(state: State):
        return {"last_completed_node": "environment", "completed_node_count": 1}

    def capacity(state: State):
        return {
            "capacity_observed_status": state["vehicle_status"],
            "last_completed_node": "capacity",
            "completed_node_count": 2,
        }

    builder = StateGraph(State)
    builder.add_node("environment", environment)
    builder.add_node("capacity", capacity)
    builder.add_edge(START, "environment")
    builder.add_edge("environment", "capacity")
    builder.add_edge("capacity", END)
    return builder.compile(checkpointer=saver, interrupt_after=["environment"])


async def seed_boundary(graph, store, session_factory, label: str):
    task_id = f"OVR-{uuid4().hex}"
    thread_id = f"cf:dispatch:{task_id}"
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    await graph.ainvoke({"vehicle_id": "vehicle-001", "vehicle_status": "NORMAL"}, config, durability="sync")
    snapshot = await graph.aget_state(config)
    checkpoint_id = snapshot.config["configurable"]["checkpoint_id"]
    with session_factory() as session:
        order_id = session.query(Order.id).limit(1).scalar()
    if order_id is None:
        raise RuntimeError("Docker seed order is missing")
    IdempotencyService(session_factory).begin(task_id, order_id, f"task-{uuid4().hex}")
    with session_factory() as session:
        row = session.query(RuntimeThread).filter_by(thread_id=thread_id).one()
        row.status = "STABLE"
        row.current_checkpoint_id = checkpoint_id
        row.state_version = 7
        row.current_node = "environment"
        row.next_node = "capacity"
        row.checkpoint_count = 4
        row.worker_consumer = label
        session.commit()
    return task_id, thread_id, checkpoint_id


def acceptance_principal(actor: str) -> AuthenticatedPrincipal:
    now = datetime.now(UTC)
    return AuthenticatedPrincipal(
        subject_id=actor,
        display_name="V2-E independent client",
        roles=frozenset({Role.SUPERVISOR}),
        permissions=ROLE_PERMISSION_MATRIX[Role.SUPERVISOR],
        auth_method=AuthMethod.DEVELOPMENT_JWT,
        issued_at=now,
        expires_at=now + timedelta(minutes=15),
        jti=f"{actor}-{uuid4().hex}",
    )


def request(key: str, *, new_value: str = "BROKEN", expected_version: int = 7) -> RuntimeOverrideRequest:
    return RuntimeOverrideRequest(
        idempotency_key=key,
        entity_type="Vehicle",
        entity_id="vehicle-001",
        field="status",
        old_value="NORMAL",
        new_value=new_value,
        reason="V2-D1 Docker telemetry acceptance",
        expected_version=expected_version,
        expected_next_node="capacity",
    )


async def run(
    database_url: str,
    redis_url: str,
    *,
    legal_samples: int = 20,
    stale_samples: int = 20,
    concurrent_samples: int = 20,
    boundary_samples: int = 20,
) -> dict[str, object]:
    if min(legal_samples, stale_samples, concurrent_samples, boundary_samples) < 1:
        raise ValueError("All runtime-override acceptance sample counts must be positive")
    if stale_samples > legal_samples:
        raise ValueError("stale_samples must not exceed legal_samples")
    redis_client = Redis.from_url(redis_url, decode_responses=False)
    info = await redis_client.info("server")
    if not str(info.get("redis_version", "")).startswith("8."):
        raise RuntimeError("V2-D1 requires real Redis 8")
    store = await RedisRuntimeCheckpointStore.from_url(
        redis_url,
        ttl_minutes=10_080,
        refresh_on_read=False,
        namespace="countyflow",
    )
    await store.setup()
    graph = build_override_graph(store.native_checkpointer)
    session_factory = build_session_factory(database_url)
    overrides = SqlAlchemyRuntimeOverrideRepository(session_factory)
    threads = SqlAlchemyRuntimeThreadRepository(session_factory)
    service = RuntimeOverrideService(
        overrides,
        threads,
        store,
        LangGraphStateUpdater(graph, store, max_checkpoint_bytes=1_048_576),
        RuntimeOverridePolicy(),
        RuntimeBoundaryLock(redis_client, ttl_ms=8_000),
    )
    concurrent_services = tuple(
        RuntimeOverrideService(
            overrides,
            threads,
            store,
            LangGraphStateUpdater(graph, store, max_checkpoint_bytes=1_048_576),
            RuntimeOverridePolicy(),
            RuntimeBoundaryLock(redis_client, ttl_ms=8_000),
        )
        for _actor in ("v2e-client-alpha", "v2e-client-beta")
    )
    service_principal = acceptance_principal("v2e-acceptance")
    concurrent_principals = tuple(
        acceptance_principal(actor) for actor in ("v2e-client-alpha", "v2e-client-beta")
    )
    thread_ids: list[str] = []
    legal = stale_blocked = race_violations = capacity_broken = concurrent_violations = 0
    applied_ids: list[str] = []
    concurrent_results: list[dict[str, object]] = []
    try:
        for index in range(legal_samples):
            _, thread_id, _ = await seed_boundary(graph, store, session_factory, f"legal-{index}")
            thread_ids.append(thread_id)
            applied = await service.apply(thread_id, request(f"legal-{uuid4().hex}"), service_principal)
            if applied.status is RuntimeOverrideStatus.APPLIED:
                legal += 1
                applied_ids.append(applied.override_id)
                exact = await store.get_exact(thread_id, applied.result_checkpoint_id)
                if exact is not None and exact.state.get("vehicle_status") == "BROKEN":
                    observed = await graph.ainvoke(None, config=exact.config, durability="sync")
                    if observed.get("capacity_observed_status") == "BROKEN":
                        capacity_broken += 1
            if index < stale_samples:
                stale = await service.apply(
                    thread_id,
                    request(f"stale-{uuid4().hex}", expected_version=7),
                    service_principal,
                )
                if stale.status is RuntimeOverrideStatus.CONFLICT:
                    stale_blocked += 1

        for index in range(concurrent_samples):
            _, thread_id, _ = await seed_boundary(graph, store, session_factory, f"concurrent-{index}")
            thread_ids.append(thread_id)
            alpha, beta = await asyncio.gather(
                concurrent_services[0].apply(
                    thread_id,
                    request(f"concurrent-alpha-{uuid4().hex}", new_value="BROKEN"),
                    concurrent_principals[0],
                ),
                concurrent_services[1].apply(
                    thread_id,
                    request(f"concurrent-beta-{uuid4().hex}", new_value="MAINTENANCE"),
                    concurrent_principals[1],
                ),
            )
            winners = [item for item in (alpha, beta) if item.status is RuntimeOverrideStatus.APPLIED]
            final_thread = threads.get_by_thread_id(thread_id)
            valid = len(winners) == 1 and final_thread is not None and final_thread.state_version == 8
            if not valid:
                concurrent_violations += 1
            concurrent_results.append(
                {
                    "round": index + 1,
                    "alpha_status": alpha.status.value,
                    "beta_status": beta.status.value,
                    "winner_count": len(winners),
                    "final_state_version": final_thread.state_version if final_thread else None,
                    "valid": valid,
                }
            )

        for index in range(boundary_samples):
            _, thread_id, _ = await seed_boundary(graph, store, session_factory, f"race-{index}")
            thread_ids.append(thread_id)
            override_task = asyncio.create_task(
                service.apply(thread_id, request(f"race-{uuid4().hex}"), service_principal)
            )

            async def worker_claim(claim_thread_id: str = thread_id):
                await asyncio.sleep(0)
                current = threads.get_by_thread_id(claim_thread_id)
                try:
                    return await asyncio.to_thread(
                        threads.claim_next_node,
                        claim_thread_id,
                        expected_checkpoint_id=current.current_checkpoint_id,
                        expected_state_version=current.state_version,
                        expected_next_node=current.next_node,
                        worker_consumer="race-worker",
                    )
                except BoundaryClaimConflict:
                    return None

            worker_task = asyncio.create_task(worker_claim())
            applied, worker = await asyncio.gather(override_task, worker_task)
            override_won = applied.status is RuntimeOverrideStatus.APPLIED
            worker_won = worker is not None
            if override_won == worker_won:
                race_violations += 1
            if override_won:
                exact = await store.get_exact(thread_id, applied.result_checkpoint_id)
                if exact is None or exact.state.get("vehicle_status") != "BROKEN":
                    race_violations += 1

        with session_factory() as session:
            timing_rows = (
                session.query(RuntimeOverrideAttempt)
                .join(RuntimeOverride, RuntimeOverride.override_id == RuntimeOverrideAttempt.override_id)
                .filter(RuntimeOverride.override_id.in_(applied_ids))
                .all()
            )
        timing_names = (
            "authorization_ms",
            "lock_ms",
            "checkpoint_read_ms",
            "state_update_ms",
            "promotion_ms",
            "total_ms",
        )
        timings = {
            name: summary([float(getattr(row, name)) for row in timing_rows if getattr(row, name) is not None])
            for name in timing_names
        }
        p99_total = timings["total_ms"]["p99_or_maximum"]
        passed = (
            legal == legal_samples
            and capacity_broken == legal_samples
            and stale_blocked == stale_samples
            and concurrent_violations == 0
            and race_violations == 0
            and 8_000 > p99_total + 2_000
        )
        return {
            "real_servers": {"mysql": True, "redis_8": True},
            "legal_overrides": {"applied": legal, "samples": legal_samples},
            "capacity_reads_broken": {"count": capacity_broken, "samples": legal_samples},
            "stale_version": {"blocked": stale_blocked, "samples": stale_samples, "silent": stale_samples - stale_blocked},
            "concurrent_override": {
                "iterations": concurrent_samples,
                "violations": concurrent_violations,
                "results": concurrent_results,
            },
            "boundary_race": {"iterations": boundary_samples, "violations": race_violations},
            "timings_ms": timings,
            "lock_ttl_ms": 8_000,
            "required_ttl_ms": round(p99_total + 2_000, 3),
            "passed": passed,
        }
    finally:
        for thread_id in thread_ids:
            await store.delete_thread(thread_id)
        await store.close()
        await redis_client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V2-D1 real MySQL/Redis override acceptance.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--redis-url", default="redis://127.0.0.1:6380/0")
    parser.add_argument("--legal-samples", type=int, default=20)
    parser.add_argument("--stale-samples", type=int, default=20)
    parser.add_argument("--concurrent-samples", type=int, default=20)
    parser.add_argument("--boundary-samples", type=int, default=20)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = asyncio.run(
        run(
            args.database_url,
            args.redis_url,
            legal_samples=args.legal_samples,
            stale_samples=args.stale_samples,
            concurrent_samples=args.concurrent_samples,
            boundary_samples=args.boundary_samples,
        )
    )
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
