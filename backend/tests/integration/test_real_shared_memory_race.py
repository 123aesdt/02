import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("COUNTYFLOW_REAL_SHARED_MEMORY_TEST") != "1",
    reason="set COUNTYFLOW_REAL_SHARED_MEMORY_TEST=1 with the four Docker stores running",
)


@pytest.mark.asyncio
async def test_real_shared_memory_visibility_races_and_recovery() -> None:
    from scripts.shared_memory_integration import run_acceptance

    result = await run_acceptance()

    assert result["qdrant_success_neo4j_failure"] == "PARTIAL_TO_APPLIED"
    assert result["neo4j_success_qdrant_failure"] == "PARTIAL_TO_APPLIED"
    assert result["staged_projection_invisible"] is True
    assert result["redis_single_lock_winner"] == 1
    assert result["mysql_single_v7_to_v8_winner"] == 1
    assert result["projection_duplicates"] == 0
