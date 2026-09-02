import asyncio

from qdrant_client import QdrantClient
from redis.asyncio import Redis

from app.core.config import get_settings
from app.graph_memory.driver import build_neo4j_driver
from app.observability.logging import configure_structured_logging
from app.observability.runtime import get_process_observability
from app.runtime import build_runtime_worker


async def run() -> None:
    settings = get_settings()
    if settings.runtime_profile in {"docker-dev", "production"}:
        configure_structured_logging(settings.worker_consumer_name, settings.runtime_profile)
    observability = get_process_observability(settings.metrics_enabled, settings.metrics_host, settings.metrics_port)
    redis_client = Redis.from_url(settings.redis_url, decode_responses=False)
    qdrant_client = QdrantClient(url=settings.qdrant_url)
    neo4j_driver = build_neo4j_driver(settings)
    worker = build_runtime_worker(settings, redis_client, qdrant_client, neo4j_driver)
    try:
        observability.runtime.start()
        await worker.startup()
        while True:
            await worker.recover_once()
            await worker.run_once()
    finally:
        await worker.shutdown()
        observability.runtime.stop()
        if neo4j_driver is not None:
            await neo4j_driver.close()
        qdrant_client.close()


if __name__ == "__main__":
    asyncio.run(run())
