from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.events.models import TaskEvent
from app.models.dispatch_publication import DispatchPublication
from app.models.task import DispatchTask

SENSITIVE_EVENT_DATA_KEYS = frozenset(
    {
        "adopted_memory_id",
        "algorithm",
        "blocked_edge_ids",
        "candidate_routes",
        "candidate_vehicles",
        "decision_reason",
        "distance_delta_km",
        "driver_id",
        "eta_delta_minutes",
        "network_edges",
        "network_nodes",
        "original_path",
        "original_route_id",
        "original_vehicle_id",
        "pickup_route",
        "recommended_path",
        "recommended_route",
        "road_network_version",
        "route_id",
        "scoring_formula",
        "selected_driver_id",
        "selected_vehicle_id",
        "target_driver_id",
        "target_route_id",
        "target_vehicle_id",
        "transfer_node_id",
        "vehicle_id",
        "vehicle_reassigned",
        "visited_node_count",
    }
)


class TaskEventVisibilityProjector:
    """Project one persisted event for its current viewer and publication state."""

    def __init__(self, session_factory: Callable[[], object]) -> None:
        self._session_factory = session_factory

    def project(self, event: TaskEvent, *, can_review: bool) -> dict[str, object]:
        payload = event.to_dict()
        data = dict(event.data or {})
        if can_review or not SENSITIVE_EVENT_DATA_KEYS.intersection(data):
            return payload
        if self._is_published(event.task_id):
            return payload
        payload["data"] = {key: value for key, value in data.items() if key not in SENSITIVE_EVENT_DATA_KEYS}
        return payload

    def _is_published(self, task_id: str) -> bool:
        try:
            with self._session_factory() as session:
                publication_id = session.scalar(
                    select(DispatchPublication.id)
                    .join(DispatchTask, DispatchPublication.task_id == DispatchTask.id)
                    .where(DispatchTask.task_id == task_id)
                    .limit(1)
                )
                return publication_id is not None
        except SQLAlchemyError:
            return False
