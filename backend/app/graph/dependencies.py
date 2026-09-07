from dataclasses import dataclass, field

from app.audit.service import AuditService
from app.capacity.service import CapacityService
from app.dispatch.service import DispatchService
from app.fleet.service import FleetAllocationService
from app.graph_memory.service import GraphMemoryService
from app.memory.service import EntityMemoryService
from app.observability.recorder import MetricsRecorder, NoOpMetricsRecorder
from app.recommendations.service import IssueRecommendationService
from app.road_network.service import RoadNetworkSnapshotService
from app.routing.service import RoutingService
from app.sandtable.service import SandtableContextService
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
    sandtable_context_service: SandtableContextService | None = None
    fleet_allocation_service: FleetAllocationService | None = None
    road_network_snapshot_service: RoadNetworkSnapshotService | None = None
    issue_recommendation_service: IssueRecommendationService = field(default_factory=IssueRecommendationService)
    metrics: MetricsRecorder = field(default_factory=NoOpMetricsRecorder)
