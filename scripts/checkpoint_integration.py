"""Benchmark the official async LangGraph saver against a real Redis 8 server."""

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

from app.runtime_threads.checkpoint_store import RedisRuntimeCheckpointStore
from langgraph.graph import END, START, StateGraph
from redis.asyncio import Redis

SAMPLE_COUNT = 20


class ProbeState(TypedDict):
    value: int


def latency_summary(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    p95_index = max(0, (95 * len(ordered) + 99) // 100 - 1)
    return {
        "minimum": round(ordered[0], 3),
        "average": round(statistics.fmean(ordered), 3),
        "p95": round(ordered[p95_index], 3),
        "maximum": round(ordered[-1], 3),
    }


async def run_acceptance(redis_url: str) -> dict[str, object]:
    redis_client = Redis.from_url(redis_url, decode_responses=False)
    info = await redis_client.info("server")
    if str(info.get("redis_version", "")).split(".", maxsplit=1)[0] != "8":
        raise RuntimeError("The checkpoint gate requires a real Redis 8 server.")
    store = await RedisRuntimeCheckpointStore.from_url(
        redis_url,
        ttl_minutes=10_080,
        refresh_on_read=False,
        namespace="countyflow",
    )
    write_latency_ms: list[float] = []
    exact_read_latency_ms: list[float] = []
    payload_bytes: list[int] = []
    errors = 0
    thread_ids: list[str] = []

    async def step(state: ProbeState) -> dict[str, int]:
        return {"value": state["value"] + 1}

    graph_builder = StateGraph(ProbeState)
    graph_builder.add_node("step", step)
    graph_builder.add_edge(START, "step")
    graph_builder.add_edge("step", END)
    graph = graph_builder.compile(checkpointer=store.native_checkpointer)
    try:
        await store.setup()
        for index in range(SAMPLE_COUNT):
            thread_id = f"cf:checkpoint-probe:{uuid4().hex}"
            thread_ids.append(thread_id)
            config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
            started = time.perf_counter()
            try:
                await graph.ainvoke({"value": index}, config=config, durability="sync")
                write_latency_ms.append((time.perf_counter() - started) * 1000)
                [latest] = await store.list_bounded(thread_id, 1)
                started = time.perf_counter()
                exact = await store.get_exact(thread_id, latest.checkpoint_id)
                exact_read_latency_ms.append((time.perf_counter() - started) * 1000)
                if exact is None:
                    raise RuntimeError("Exact checkpoint read returned no record.")
                payload_bytes.append(exact.serialized_size_bytes)
            except Exception:
                errors += 1
                raise
        if len(write_latency_ms) < SAMPLE_COUNT or len(exact_read_latency_ms) < SAMPLE_COUNT:
            raise RuntimeError("Checkpoint benchmark produced fewer than 20 writes/reads.")
        if max(payload_bytes) > 1_048_576:
            raise RuntimeError("Checkpoint payload exceeded 1 MiB.")
        return {
            "server": "Redis 8",
            "samples": SAMPLE_COUNT,
            "write_latency_ms": latency_summary(write_latency_ms),
            "exact_read_latency_ms": latency_summary(exact_read_latency_ms),
            "payload_bytes": {
                "minimum": min(payload_bytes),
                "average": round(statistics.fmean(payload_bytes), 3),
                "p95": sorted(payload_bytes)[18],
                "maximum": max(payload_bytes),
            },
            "errors": errors,
            "passed": errors == 0 and max(payload_bytes) <= 1_048_576,
        }
    finally:
        for thread_id in thread_ids:
            await store.delete_thread(thread_id)
        await store.close()
        await redis_client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 20 official Redis checkpoint writes and exact reads.")
    parser.add_argument("--redis-url", default="redis://127.0.0.1:6380/0")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = asyncio.run(run_acceptance(args.redis_url))
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
