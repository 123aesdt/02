"""Verify persistence across per-store and full Compose restarts."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from time import monotonic
from uuid import uuid4

import httpx
from neo4j import AsyncGraphDatabase
from qdrant_client import QdrantClient
from redis.asyncio import Redis
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.runtime_overrides.redis_lock import RuntimeBoundaryLock

MYSQL_TABLES = (
    "runtime_threads",
    "shared_memory_facts",
    "runtime_overrides",
    "dispatches",
    "audit_records",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--source-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def command(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return command(os.environ["DOCKER_COMMAND"], "compose", "--env-file", ".docker.env", *args, check=check)


async def wait_http(timeout: float = 90.0) -> None:
    deadline = monotonic() + timeout
    async with httpx.AsyncClient(timeout=2.0) as client:
        while monotonic() < deadline:
            try:
                response = await client.get("http://127.0.0.1:8001/health")
                if response.status_code == 200 and response.json().get("status") == "ok":
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.5)
    raise TimeoutError("Backend did not become healthy")


async def retry(operation, *, timeout: float = 60.0):
    deadline = monotonic() + timeout
    last_error: Exception | None = None
    while monotonic() < deadline:
        try:
            return await operation()
        except Exception as error:  # noqa: BLE001 - bounded readiness retry spans four vendor clients
            last_error = error
            await asyncio.sleep(0.5)
    raise RuntimeError("Store did not become ready after restart") from last_error


def mysql_snapshot(database_url: str) -> dict[str, int]:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            return {table: int(connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()) for table in MYSQL_TABLES}
    finally:
        engine.dispose()


async def neo4j_snapshot(uri: str, password: str) -> dict[str, object]:
    driver = AsyncGraphDatabase.driver(uri, auth=(os.environ.get("NEO4J_USER", "neo4j"), password))
    try:
        await driver.verify_connectivity()
        database = os.environ.get("NEO4J_DATABASE", "neo4j")
        entities, _, _ = await driver.execute_query("MATCH (n:GraphEntity) RETURN count(n) AS count", database_=database)
        relations, _, _ = await driver.execute_query("MATCH (:GraphEntity)-[r]->(:GraphEntity) RETURN count(r) AS count", database_=database)
        projections, _, _ = await driver.execute_query(
            "MATCH ()-[r]->() WHERE r.control_fact_key IS NOT NULL RETURN r.projection_status AS status, count(r) AS count ORDER BY status",
            database_=database,
        )
        constraints, _, _ = await driver.execute_query("SHOW CONSTRAINTS YIELD name RETURN name ORDER BY name", database_=database)
        indexes, _, _ = await driver.execute_query("SHOW INDEXES YIELD name RETURN name ORDER BY name", database_=database)
        return {
            "entities": int(entities[0]["count"]),
            "relations": int(relations[0]["count"]),
            "projection_statuses": {str(item["status"]): int(item["count"]) for item in projections},
            "constraints": [str(item["name"]) for item in constraints],
            "indexes": [str(item["name"]) for item in indexes],
        }
    finally:
        await driver.close()


def qdrant_snapshot(url: str) -> dict[str, int]:
    client = QdrantClient(url=url, check_compatibility=False)
    try:
        return {
            item.name: int(client.get_collection(item.name).points_count or 0)
            for item in client.get_collections().collections
        }
    finally:
        client.close()


async def runtime_snapshot(task_id: str, thread_id: str, redis_client: Redis) -> dict[str, object]:
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8001", timeout=10.0) as client:
        thread = (await client.get(f"/api/v1/runtime/threads/{thread_id}")).json()
        history = (await client.get(f"/api/v1/runtime/threads/{thread_id}/history?limit=100")).json()
    event_key = f"countyflow:events:task:{task_id}"
    pending = await redis_client.xpending("countyflow:dispatch:tasks", "countyflow-workers")
    return {
        "checkpoint_id": thread.get("current_checkpoint_id"),
        "state_version": thread.get("state_version"),
        "vehicle_status": (thread.get("state") or {}).get("vehicle_status"),
        "checkpoint_available": thread.get("checkpoint_available"),
        "checkpoint_history": len(history.get("items", [])),
        "task_event_count": int(await redis_client.xlen(event_key)),
        "task_stream_pending": int(pending["pending"]),
    }


async def run(args: argparse.Namespace) -> dict[str, object]:
    source = json.loads(args.source_evidence.read_text(encoding="utf-8"))
    task_id = str(source["context"]["task_id"])
    thread_id = str(source["context"]["thread_id"])
    password = os.environ.get("NEO4J_PASSWORD", "")
    if not password:
        raise RuntimeError("Neo4j password is required")
    redis_url = "redis://127.0.0.1:6380/0"
    redis_client = Redis.from_url(redis_url, decode_responses=False)
    marker_key = f"v2e:restart:{uuid4().hex}"
    marker_value = uuid4().hex
    await redis_client.set(marker_key, marker_value)
    lock = RuntimeBoundaryLock(redis_client, ttl_ms=120_000)
    lock_probe = f"v2e-restart-{uuid4().hex}"
    lock_handle = await lock.acquire(lock_probe)
    if not lock_handle.acquired:
        raise AssertionError("Could not acquire restart lock probe")
    before = {
        "mysql": mysql_snapshot(args.database_url),
        "neo4j": await neo4j_snapshot("bolt://127.0.0.1:7687", password),
        "qdrant": qdrant_snapshot("http://127.0.0.1:6333"),
        "runtime": await runtime_snapshot(task_id, thread_id, redis_client),
    }
    steps: dict[str, object] = {}
    try:
        compose("restart", "mysql")
        mysql_after = await retry(lambda: asyncio.to_thread(mysql_snapshot, args.database_url))
        steps["mysql_restart"] = {"passed": mysql_after == before["mysql"], "after": mysql_after}

        compose("restart", "neo4j")
        neo4j_after = await retry(lambda: neo4j_snapshot("bolt://127.0.0.1:7687", password))
        steps["neo4j_restart"] = {"passed": neo4j_after == before["neo4j"], "after": neo4j_after}

        compose("restart", "qdrant")
        qdrant_after = await retry(lambda: asyncio.to_thread(qdrant_snapshot, "http://127.0.0.1:6333"))
        steps["qdrant_restart"] = {"passed": qdrant_after == before["qdrant"], "after": qdrant_after}

        compose("restart", "redis")

        async def redis_ready() -> bool:
            return bool(await redis_client.ping())

        await retry(redis_ready)
        contender = await RuntimeBoundaryLock(redis_client, ttl_ms=120_000).acquire(lock_probe)
        lock_preserved = not contender.acquired
        lock_released = await lock.release(lock_handle)
        await wait_http()
        runtime_after_redis = await runtime_snapshot(task_id, thread_id, redis_client)
        marker_after_redis = await redis_client.get(marker_key)
        steps["redis_restart"] = {
            "passed": (
                marker_after_redis == marker_value.encode()
                and lock_preserved
                and lock_released
                and runtime_after_redis == before["runtime"]
            ),
            "aof_marker_persisted": marker_after_redis == marker_value.encode(),
            "lock_preserved": lock_preserved,
            "lock_owner_release": lock_released,
            "runtime": runtime_after_redis,
        }

        compose("down")
        compose("up", "-d")
        await wait_http()
        redis_after_full = Redis.from_url(redis_url, decode_responses=False)
        try:
            full = {
                "mysql": await retry(lambda: asyncio.to_thread(mysql_snapshot, args.database_url)),
                "neo4j": await retry(lambda: neo4j_snapshot("bolt://127.0.0.1:7687", password)),
                "qdrant": await retry(lambda: asyncio.to_thread(qdrant_snapshot, "http://127.0.0.1:6333")),
                "runtime": await retry(lambda: runtime_snapshot(task_id, thread_id, redis_after_full)),
                "marker_persisted": await redis_after_full.get(marker_key) == marker_value.encode(),
            }
        finally:
            await redis_after_full.aclose()
        full_passed = (
            full["mysql"] == before["mysql"]
            and full["neo4j"] == before["neo4j"]
            and full["qdrant"] == before["qdrant"]
            and full["runtime"] == before["runtime"]
            and full["marker_persisted"] is True
        )
        running = compose("ps", "--services", "--status", "running").stdout.splitlines()
        all_services = compose("config", "--services").stdout.splitlines()
        migration = json.loads(compose("ps", "-a", "--format", "json", "migration").stdout.strip())
        steps["compose_full_restart"] = {
            "passed": full_passed and len(all_services) == 9 and len(running) == 8 and int(migration["ExitCode"]) == 0,
            "after": full,
            "services": all_services,
            "running_services": running,
            "migration_exit_code": int(migration["ExitCode"]),
            "volumes_removed": False,
        }
        return {
            "passed": all(bool(step["passed"]) for step in steps.values()),
            "source_task_id": task_id,
            "source_thread_id": thread_id,
            "before": before,
            "steps": steps,
        }
    finally:
        await redis_client.delete(marker_key)
        await redis_client.aclose()


def main() -> None:
    args = parse_args()
    payload = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": payload["passed"], "steps": payload["steps"]}, ensure_ascii=False))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
