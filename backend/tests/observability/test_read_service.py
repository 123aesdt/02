from datetime import UTC, datetime

import pytest

from app.observability.prometheus import PrometheusSample
from app.observability.query_catalog import ObservabilityQueryKey
from app.observability.service import ObservabilityReadService


class LabeledClient:
    async def instant(self, key: ObservabilityQueryKey, window: str) -> tuple[PrometheusSample, ...]:
        now = datetime.now(UTC).timestamp()
        if key is ObservabilityQueryKey.DEPENDENCY_UP:
            return (
                PrometheusSample(1, now, {"dependency": "mysql"}),
                PrometheusSample(0, now, {"dependency": "neo4j"}),
            )
        return (PrometheusSample(1, now, {}),)


@pytest.mark.asyncio
async def test_read_service_preserves_only_bounded_series_and_safe_aggregate() -> None:
    result = await ObservabilityReadService(LabeledClient()).summary("5m")

    assert result.metrics["dependency_up"] == 0
    assert result.series["dependency_up"] == {"mysql": 1, "neo4j": 0}
