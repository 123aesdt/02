from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    driver_id: str
    route_id: str
    anomaly_type: str
    resolution_text: str
    metadata: dict
    created_at: datetime


@dataclass(frozen=True)
class MemoryRecall:
    memory_id: str
    similarity_score: float
    driver_id: str
    route_id: str
    anomaly_type: str
    historical_resolution: str
    metadata: dict
