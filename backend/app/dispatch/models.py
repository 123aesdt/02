from dataclasses import dataclass


@dataclass(frozen=True)
class DispatchResult:
    dispatch_id: int | None
    dispatch_no: str | None
    order_id: int
    task_id: str
    status: str
    original_route_id: str
    target_route_id: str | None
    version: int | None
    executed: bool
    reason: str
    requires_manual_review: bool
