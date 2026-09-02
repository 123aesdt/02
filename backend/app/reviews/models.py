from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ReviewDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


@dataclass(frozen=True)
class ReviewDecisionResult:
    task_id: str
    decision: ReviewDecision
    status: str
    reviewer: str
    decided_at: datetime
    dispatch_version: int

