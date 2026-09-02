from dataclasses import dataclass, field

from app.audit.service import AuditService
from app.capacity.service import CapacityService
from app.dispatch.service import DispatchService
from app.graph_memory.service import GraphMemoryService
from app.memory.service import EntityMemoryService
from app.observability.recorder import MetricsRecorder, NoOpMetricsRecorder
from app.recommendations.service import IssueRecommendationService
from app.routing.service import RoutingService
from app.services.environment import EnvironmentService


@dataclass(frozen=True)
class GraphDependencies:
    audit_service: AuditService | None = None
    capacity_service: CapacityService | None = None
    dispatch_service: DispatchService | None = None
    entity_memory_service: EntityMemoryService | None = None
    graph_memory_service: GraphMemoryService | None = None
    environment_service: EnvironmentService | None = None
    routing_service: RoutingService | None = None
    issue_recommendation_service: IssueRecommendationService = field(default_factory=IssueRecommendationService)
    metrics: MetricsRecorder = field(default_factory=NoOpMetricsRecorder)
