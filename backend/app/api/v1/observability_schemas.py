from typing import Literal

from pydantic import BaseModel, Field


class ObservabilitySummaryResponse(BaseModel):
    state: Literal["LIVE", "STALE"]
    window: Literal["5m", "15m", "1h"]
    timestamp: str
    metrics: dict[str, object]
    grafana_url: str | None = None
    series: dict[str, dict[str, float]] = Field(default_factory=dict)
