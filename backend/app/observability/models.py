from dataclasses import dataclass, field
from enum import StrEnum


class ObservabilityState(StrEnum):
    LIVE = "LIVE"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class ObservabilitySummary:
    state: ObservabilityState
    window: str
    timestamp: str
    metrics: dict[str, object]
    grafana_url: str | None = None
    series: dict[str, dict[str, float]] = field(default_factory=dict)
