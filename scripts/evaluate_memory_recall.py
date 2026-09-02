"""Run the deterministic functional Qdrant recall benchmark; not a real semantic benchmark."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from app.memory.models import MemoryRecord
from app.memory.qdrant_repository import QdrantMemoryRepository
from app.memory.service import EntityMemoryService
from app.providers.embedding.fake import FakeEmbeddingProvider
from qdrant_client import QdrantClient


async def main():
    service = EntityMemoryService(
        FakeEmbeddingProvider(128),
        QdrantMemoryRepository(QdrantClient(":memory:"), "benchmark", 128),
    )
    await service.remember(
        MemoryRecord(
            "memory-rain-li",
            "driver-li",
            "xinping-road",
            "rain_slippery",
            "建议改走102国道",
            {"text": "李师傅 雨天 新平路 道路湿滑"},
            datetime.now(UTC),
        )
    )
    cases = json.loads(
        (
            Path(__file__).parents[1]
            / "backend/tests/benchmarks/memory_recall_cases.json"
        ).read_text(encoding="utf-8")
    )
    correct = 0
    for case in cases:
        recall = await service.recall(case["query"], 1)
        correct += recall[0].memory_id == case["expected_memory_id"]
    print(
        {
            "total": len(cases),
            "correct": correct,
            "top1_accuracy": correct / len(cases),
            "benchmark": "functional",
        }
    )


asyncio.run(main())
