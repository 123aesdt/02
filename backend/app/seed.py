import asyncio
from datetime import UTC, datetime
from types import MappingProxyType

from qdrant_client import QdrantClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import build_session_factory
from app.graph_memory.driver import build_neo4j_driver
from app.graph_memory.neo4j_repository import Neo4jGraphMemoryRepository
from app.graph_memory.schema import bootstrap_graph_schema
from app.graph_memory.seed import seed_graph_memory
from app.memory.models import MemoryRecord
from app.memory.qdrant_repository import QdrantMemoryRepository
from app.memory.service import EntityMemoryService
from app.models.anomaly import Anomaly
from app.models.audit import AuditRecord
from app.models.demo_employee_account import DemoEmployeeAccount
from app.models.dispatch import Dispatch
from app.models.order import Order
from app.models.runtime_thread import RuntimeThread
from app.models.task import DispatchTask
from app.providers.embedding.fake import FakeEmbeddingProvider
from app.sandtable.seed_data import ORDERS, STATIONS, VEHICLES
from app.sandtable.sqlalchemy_repository import seed_new_county_sandtable

DEVELOPMENT_RUNTIME_PROFILES = frozenset({"local", "test", "docker-dev"})
DEMO_RUNTIME_STATUSES = ("RUNNING", "STABLE", "OVERRIDING", "TERMINAL")
DEMO_DELIVERY_EMPLOYEE_SUBJECT_IDS = ("CF-DEMO-001", "CF-DEMO-006")

DEMO_REPORT_ROUTES = (
    ("ROUTE-01", "新平县中心仓", "城东配送站"),
    ("ROUTE-02", "新平县中心仓", "102 国道东口"),
    ("ROUTE-03", "新平县中心仓", "北岭村驿站"),
    ("ROUTE-04", "新平县中心仓", "河西乡服务站"),
    ("ROUTE-05", "新平县中心仓", "南山村服务点"),
    ("ROUTE-06", "新平冷链中心", "102 国道中段"),
    ("ROUTE-07", "新平县中心仓", "双河村路口"),
    ("ROUTE-08", "新平县中心仓", "城东电商服务点"),
    ("ROUTE-09", "北岭村驿站", "102 国道西口"),
    ("ROUTE-10", "县域车辆维修站", "102 国道中段"),
)


def _demo_report_source_spec(position: int) -> MappingProxyType:
    suffix = f"{position:03d}"
    route_id, origin, destination = DEMO_REPORT_ROUTES[(position - 1) // 2]
    task_id = (
        "DEMO-TASK-REPORT-VEHICLE"
        if position == 1
        else "DEMO-TASK-REPORT-ROAD"
        if position == 8
        else f"DEMO-TASK-REPORT-{suffix}"
    )
    idempotency_key = (
        "demo-report-source-vehicle"
        if position == 1
        else "demo-report-source-road"
        if position == 8
        else f"demo-report-source-{suffix}"
    )
    return MappingProxyType(
        {
            "task_id": task_id,
            "order_no": f"DEMO-REPORT-ORDER-{suffix}",
            "idempotency_key": idempotency_key,
            "vehicle_id": f"V-{suffix}",
            "route_id": route_id,
            "origin": origin,
            "destination": destination,
        }
    )


DEMO_REPORT_SOURCE_TASKS = tuple(_demo_report_source_spec(position) for position in range(1, 21))

DEMO_EMPLOYEE_ACCOUNTS = (
    MappingProxyType({"employee_id": "CF-DEMO-001", "display_name": "张师傅", "role": "EMPLOYEE"}),
    MappingProxyType({"employee_id": "CF-DEMO-002", "display_name": "李运营", "role": "OPERATOR"}),
    MappingProxyType({"employee_id": "CF-DEMO-003", "display_name": "王主管", "role": "SUPERVISOR"}),
    MappingProxyType({"employee_id": "CF-DEMO-004", "display_name": "赵审计", "role": "AUDITOR"}),
    MappingProxyType({"employee_id": "CF-DEMO-005", "display_name": "系统管理员", "role": "ADMIN"}),
    MappingProxyType({"employee_id": "CF-DEMO-006", "display_name": "陈师傅", "role": "EMPLOYEE"}),
    MappingProxyType({"employee_id": "CF-DEMO-007", "display_name": "孙调度", "role": "DISPATCHER"}),
)

DEMO_BUSINESS_CASES = (
    MappingProxyType(
        {
            "order_no": "LEGACY-DEMO-ORDER-001",
            "legacy_order_no": "DEMO-ORDER-001",
            "status": "IN_TRANSIT",
            "driver_id": "demo-driver-li",
            "vehicle_id": "demo-vehicle-001",
            "route_id": "xinping-county-road",
            "origin": "新平县城关镇冷链配送中心",
            "destination": "大山镇卫生院",
            "anomaly_no": "DEMO-ANOM-001",
            "anomaly_type": "rain_slippery",
            "severity": "HIGH",
            "description": "新平县强降雨后县道湿滑，冷链药品配送需评估绕行。",
        }
    ),
    MappingProxyType(
        {
            "order_no": "LEGACY-DEMO-ORDER-002",
            "legacy_order_no": "DEMO-ORDER-002",
            "status": "IN_TRANSIT",
            "driver_id": "demo-driver-zhang",
            "vehicle_id": "demo-vehicle-002",
            "route_id": "yunling-mountain-pass",
            "origin": "云岭县白沙村农资转运点",
            "destination": "石门镇供销社",
            "anomaly_no": "DEMO-ANOM-002",
            "anomaly_type": "landslide_roadblock",
            "severity": "HIGH",
            "description": "云岭县山口路段发生小型塌方，农资车辆暂时无法通行。",
        }
    ),
    MappingProxyType(
        {
            "order_no": "LEGACY-DEMO-ORDER-003",
            "legacy_order_no": "DEMO-ORDER-003",
            "status": "IN_TRANSIT",
            "driver_id": "demo-driver-chen",
            "vehicle_id": "demo-vehicle-003",
            "route_id": "hegu-tea-route",
            "origin": "河谷县茶叶集散中心",
            "destination": "青塘乡合作社",
            "anomaly_no": "DEMO-ANOM-003",
            "anomaly_type": "fog_visibility",
            "severity": "MEDIUM",
            "description": "河谷县清晨浓雾影响茶叶运输视距，建议降低山区道路车速。",
        }
    ),
    MappingProxyType(
        {
            "order_no": "LEGACY-DEMO-ORDER-004",
            "legacy_order_no": "DEMO-ORDER-004",
            "status": "IN_TRANSIT",
            "driver_id": "demo-driver-wang",
            "vehicle_id": "demo-vehicle-004",
            "route_id": "dongchuan-rural-loop",
            "origin": "东川区快递分拨中心",
            "destination": "岚山村服务点",
            "anomaly_no": "DEMO-ANOM-004",
            "anomaly_type": "vehicle_breakdown",
            "severity": "HIGH",
            "description": "东川区农村环线车辆发动机告警，包裹配送需等待救援车辆。",
        }
    ),
    MappingProxyType(
        {
            "order_no": "LEGACY-DEMO-ORDER-005",
            "legacy_order_no": "DEMO-ORDER-005",
            "status": "IN_TRANSIT",
            "driver_id": "demo-driver-lin",
            "vehicle_id": "demo-vehicle-005",
            "route_id": "anping-market-road",
            "origin": "安平县粮油仓储中心",
            "destination": "青峰镇中学",
            "anomaly_no": "DEMO-ANOM-005",
            "anomaly_type": "traffic_congestion",
            "severity": "MEDIUM",
            "description": "安平县集市日主干道拥堵，学校食材配送可能晚点。",
        }
    ),
    MappingProxyType(
        {
            "order_no": "LEGACY-DEMO-ORDER-006",
            "legacy_order_no": "DEMO-ORDER-006",
            "status": "IN_TRANSIT",
            "driver_id": "demo-driver-huang",
            "vehicle_id": "demo-vehicle-006",
            "route_id": "liucheng-clinic-route",
            "origin": "柳城县药品配送站",
            "destination": "马家沟村卫生室",
            "anomaly_no": "DEMO-ANOM-006",
            "anomaly_type": "heatwave_cold_chain",
            "severity": "HIGH",
            "description": "柳城县持续高温，药品冷链车制冷负荷偏高，需要优先送达。",
        }
    ),
    MappingProxyType(
        {
            "order_no": "LEGACY-DEMO-ORDER-007",
            "legacy_order_no": "DEMO-ORDER-007",
            "status": "IN_TRANSIT",
            "driver_id": "demo-driver-zhou",
            "vehicle_id": "demo-vehicle-007",
            "route_id": "songxi-north-ridge",
            "origin": "松溪县生鲜仓",
            "destination": "北岭村驿站",
            "anomaly_no": "DEMO-ANOM-007",
            "anomaly_type": "cold_chain_temperature",
            "severity": "MEDIUM",
            "description": "松溪县北岭村上坡路段较长，生鲜车厢温度接近预警阈值。",
        }
    ),
    MappingProxyType(
        {
            "order_no": "LEGACY-DEMO-ORDER-008",
            "legacy_order_no": "DEMO-ORDER-008",
            "status": "IN_TRANSIT",
            "driver_id": "demo-driver-xu",
            "vehicle_id": "demo-vehicle-008",
            "route_id": "nanxi-red-rock-road",
            "origin": "南溪县电商仓",
            "destination": "红岩乡助农服务点",
            "anomaly_no": "DEMO-ANOM-008",
            "anomaly_type": "road_construction",
            "severity": "LOW",
            "description": "南溪县红岩乡道路养护施工，预计单向交替放行十分钟。",
        }
    ),
    MappingProxyType(
        {
            "order_no": "LEGACY-DEMO-ORDER-009",
            "legacy_order_no": "DEMO-ORDER-009",
            "status": "IN_TRANSIT",
            "driver_id": "demo-driver-guo",
            "vehicle_id": "demo-vehicle-009",
            "route_id": "quanyuan-double-river",
            "origin": "泉源县农机服务站",
            "destination": "双河镇维修点",
            "anomaly_no": "DEMO-ANOM-009",
            "anomaly_type": "bridge_inspection",
            "severity": "LOW",
            "description": "泉源县双河桥开展例行检测，农机配件运输需按限速通行。",
        }
    ),
    MappingProxyType(
        {
            "order_no": "LEGACY-DEMO-ORDER-010",
            "legacy_order_no": "DEMO-ORDER-010",
            "status": "IN_TRANSIT",
            "driver_id": "demo-driver-yang",
            "vehicle_id": "demo-vehicle-010",
            "route_id": "qingshan-bamboo-route",
            "origin": "青山县邮政分拨中心",
            "destination": "竹林村便民服务站",
            "anomaly_no": "DEMO-ANOM-010",
            "anomaly_type": "rainwater_detour",
            "severity": "LOW",
            "description": "青山县竹林村支路积水已开始消退，邮政车辆可按临时绕行方案通行。",
        }
    ),
)


class LegacyDemoOrderConflictError(ValueError):
    pass


def _legacy_order_matches(order: Order, case: MappingProxyType) -> bool:
    return (
        order.status,
        order.driver_id,
        order.vehicle_id,
        order.route_id,
        order.origin,
        order.destination,
        order.cargo_weight_kg,
        order.cargo_type,
        order.origin_station_id,
        order.destination_station_id,
    ) == (
        case["status"],
        case["driver_id"],
        case["vehicle_id"],
        case["route_id"],
        case["origin"],
        case["destination"],
        None,
        None,
        None,
        None,
    )


def _sandtable_order_matches(order: Order, order_no: str) -> bool:
    row = next((item for item in ORDERS if item["order_no"] == order_no), None)
    if row is None:
        return False
    station_names = {item["station_id"]: item["name"] for item in STATIONS}
    return (
        order.status,
        order.driver_id,
        order.vehicle_id,
        order.route_id,
        order.origin,
        order.destination,
        str(order.cargo_weight_kg),
        order.cargo_type,
        order.origin_station_id,
        order.destination_station_id,
    ) == (
        row["status"],
        None,
        row["vehicle_id"],
        None,
        station_names[row["origin_station_id"]],
        station_names[row["destination_station_id"]],
        row["cargo_weight_kg"],
        row["cargo_type"],
        row["origin_station_id"],
        row["destination_station_id"],
    )


def migrate_legacy_demo_business_case_orders(session: Session) -> None:
    pending: list[tuple[Order, MappingProxyType]] = []
    for case in DEMO_BUSINESS_CASES:
        legacy = session.scalar(select(Order).where(Order.order_no == case["order_no"]))
        if legacy is not None:
            continue
        old_order = session.scalar(select(Order).where(Order.order_no == case["legacy_order_no"]))
        if old_order is None or _sandtable_order_matches(old_order, case["legacy_order_no"]):
            continue
        if not _legacy_order_matches(old_order, case):
            raise LegacyDemoOrderConflictError(f"旧演示订单键冲突且指纹不匹配: {case['legacy_order_no']}")
        pending.append((old_order, case))
    for old_order, case in pending:
        old_order.order_no = case["order_no"]


def seed_demo_employee_accounts(session: Session) -> None:
    for account in DEMO_EMPLOYEE_ACCOUNTS:
        existing = session.get(DemoEmployeeAccount, account["employee_id"])
        if existing is None:
            session.add(
                DemoEmployeeAccount(
                    employee_id=account["employee_id"],
                    display_name=account["display_name"],
                    role=account["role"],
                    is_active=True,
                )
            )
        else:
            existing.display_name = account["display_name"]
            existing.role = account["role"]


def seed_demo_business_cases(session: Session) -> None:
    for position, case in enumerate(DEMO_BUSINESS_CASES, start=1):
        order = session.scalar(select(Order).where(Order.order_no == case["order_no"]))
        if order is None:
            order = Order(
                order_no=case["order_no"],
                status=case["status"],
                driver_id=case["driver_id"],
                vehicle_id=case["vehicle_id"],
                route_id=case["route_id"],
                origin=case["origin"],
                destination=case["destination"],
            )
            session.add(order)
            session.flush()
        anomaly = session.scalar(select(Anomaly).where(Anomaly.anomaly_no == case["anomaly_no"]))
        if anomaly is None:
            anomaly = Anomaly(
                anomaly_no=case["anomaly_no"],
                order_id=order.id,
                anomaly_type=case["anomaly_type"],
                severity=case["severity"],
                description=case["description"],
                status="OPEN",
            )
            session.add(anomaly)
            session.flush()
        seed_demo_execution_case(session, case, order, anomaly, position)


def seed_demo_execution_case(
    session: Session,
    case: MappingProxyType,
    order: Order,
    anomaly: Anomaly,
    position: int,
) -> None:
    suffix = f"{position:03d}"
    task_key = f"demo-seed-{suffix}"
    task = session.scalar(select(DispatchTask).where(DispatchTask.idempotency_key == task_key))
    requires_review = case["severity"] == "HIGH"
    if task is None:
        task = DispatchTask(
            task_id=f"DEMO-TASK-{suffix}",
            order_id=order.id,
            anomaly_id=anomaly.id,
            status="REVIEW_REQUIRED" if requires_review else "APPROVED",
            idempotency_key=task_key,
            started_at=datetime.now(UTC),
            completed_at=None if requires_review else datetime.now(UTC),
        )
        session.add(task)
        session.flush()
    expected_assignee = DEMO_DELIVERY_EMPLOYEE_SUBJECT_IDS[(position - 1) % len(DEMO_DELIVERY_EMPLOYEE_SUBJECT_IDS)]
    if task.idempotency_key == task_key:
        task.assignee_subject_id = expected_assignee

    dispatch_no = f"DEMO-DISPATCH-{suffix}"
    dispatch = session.scalar(select(Dispatch).where(Dispatch.dispatch_no == dispatch_no))
    if dispatch is None:
        dispatch = Dispatch(
            dispatch_no=dispatch_no,
            order_id=order.id,
            task_id=task.id,
            original_driver_id=case["driver_id"],
            target_driver_id=case["driver_id"],
            original_route_id=case["route_id"],
            target_route_id=f"{case['route_id']}-安全绕行",
            decision_reason=f"针对{case['description']}生成县域安全调度建议。",
            fallback_used=False,
            status="PENDING_REVIEW" if requires_review else "APPROVED",
        )
        session.add(dispatch)
        session.flush()

    audit = session.scalar(
        select(AuditRecord).where(
            AuditRecord.task_id == task.id,
            AuditRecord.dispatch_id == dispatch.id,
        )
    )
    if audit is None:
        session.add(
            AuditRecord(
                task_id=task.id,
                dispatch_id=dispatch.id,
                result="REVIEW_REQUIRED" if requires_review else "APPROVED",
                reason=("高风险异常需要调度主管复核后执行。" if requires_review else "风险与绕行方案已通过自动安全审计。"),
                evidence_json='{"data_provenance":"DEMO","source":"development_seed"}',
            )
        )

    thread_id = f"demo-thread-{suffix}"
    thread = session.scalar(select(RuntimeThread).where(RuntimeThread.thread_id == thread_id))
    if thread is None:
        runtime_status = DEMO_RUNTIME_STATUSES[(position - 1) % len(DEMO_RUNTIME_STATUSES)]
        terminal = runtime_status == "TERMINAL"
        current_node = "audit" if terminal else ("routing" if requires_review else "environment")
        session.add(
            RuntimeThread(
                thread_id=thread_id,
                task_id=task.task_id,
                status=runtime_status,
                current_checkpoint_id=f"demo-checkpoint-{suffix}",
                state_version=position + 1,
                current_node=current_node,
                next_node=None if terminal else ("audit" if requires_review else "routing"),
                checkpoint_count=position + 1,
                checkpoint_size_bytes=1024 + position * 128,
                worker_consumer=f"countyflow-worker-{1 + position % 2}",
                resumed_count=1 if runtime_status == "OVERRIDING" else 0,
                terminal_at=datetime.now(UTC) if terminal else None,
            )
        )


def seed_docker_e2e_case(session: Session) -> None:
    order = session.scalar(select(Order).where(Order.order_no == "ORDER-E2E-RAIN-001"))
    if order is None:
        order = Order(
            order_no="ORDER-E2E-RAIN-001",
            status="IN_TRANSIT",
            driver_id="driver-li",
            vehicle_id="vehicle-001",
            route_id="xinping-road",
            origin="新平县中心仓",
            destination="大山镇卫生院",
        )
        session.add(order)
        session.flush()
    anomaly = session.scalar(select(Anomaly).where(Anomaly.anomaly_no == "ANOM-E2E-RAIN-001"))
    if anomaly is None:
        session.add(
            Anomaly(
                anomaly_no="ANOM-E2E-RAIN-001",
                order_id=order.id,
                anomaly_type="rain_slippery",
                severity="HIGH",
                description="李师傅在雨天经过新平路，道路出现湿滑风险。",
                status="OPEN",
            )
        )


def seed_demo_report_source_tasks(session: Session) -> None:
    for spec in DEMO_REPORT_SOURCE_TASKS:
        order = session.scalar(select(Order).where(Order.order_no == spec["order_no"]))
        vehicle = next((row for row in VEHICLES if row["vehicle_id"] == spec["vehicle_id"]), None)
        driver_id = vehicle["assigned_driver_id"] if vehicle and vehicle["assigned_driver_id"] else "D-001"
        if order is None:
            order = Order(
                order_no=spec["order_no"],
                status="IN_TRANSIT",
                driver_id=driver_id,
                vehicle_id=spec["vehicle_id"],
                route_id=spec["route_id"],
                origin=spec["origin"],
                destination=spec["destination"],
            )
            session.add(order)
            session.flush()
        else:
            order.status = "IN_TRANSIT"
            order.driver_id = driver_id
            order.vehicle_id = spec["vehicle_id"]
            order.route_id = spec["route_id"]
            order.origin = spec["origin"]
            order.destination = spec["destination"]
        task = session.scalar(
            select(DispatchTask).where(DispatchTask.idempotency_key == spec["idempotency_key"])
        )
        if task is None:
            task = DispatchTask(
                task_id=spec["task_id"],
                order_id=order.id,
                anomaly_id=None,
                status="IN_PROGRESS",
                idempotency_key=spec["idempotency_key"],
                assignee_subject_id="CF-DEMO-001",
            )
            session.add(task)
        else:
            task.order_id = order.id
            task.status = "IN_PROGRESS"
            task.assignee_subject_id = "CF-DEMO-001"


def seed_database(session_factory=None, runtime_profile: str | None = None) -> None:
    profile = runtime_profile or get_settings().runtime_profile
    if profile not in DEVELOPMENT_RUNTIME_PROFILES:
        return
    factory = session_factory or build_session_factory()
    with factory() as session:
        seed_demo_employee_accounts(session)
        migrate_legacy_demo_business_case_orders(session)
        seed_new_county_sandtable(session)
        seed_demo_report_source_tasks(session)
        seed_docker_e2e_case(session)
        seed_demo_business_cases(session)
        session.commit()


async def seed_memory() -> None:
    settings = get_settings()
    if settings.runtime_profile not in DEVELOPMENT_RUNTIME_PROFILES:
        return
    client = QdrantClient(url=settings.qdrant_url)
    try:
        embedding = FakeEmbeddingProvider(dimension=settings.embedding_dimension)
        service = EntityMemoryService(
            embedding,
            QdrantMemoryRepository(client, "entity_resolution_memory", embedding.vector_dimension),
        )
        await service.remember(
            MemoryRecord(
                memory_id="memory-rain-li",
                driver_id="driver-li",
                route_id="xinping-road",
                anomaly_type="rain_slippery",
                resolution_text="建议改走102国道",
                metadata={
                    "text": "李师傅在雨天经过新平路时道路湿滑风险较高。",
                    "data_provenance": "DEMO",
                },
                created_at=datetime.now(UTC),
            )
        )
    finally:
        client.close()


async def seed_graph() -> None:
    settings = get_settings()
    if settings.runtime_profile not in DEVELOPMENT_RUNTIME_PROFILES:
        return
    if settings.graph_memory_backend != "neo4j":
        return
    driver = build_neo4j_driver(settings)
    if driver is None:
        return
    try:
        await driver.verify_connectivity()
        await bootstrap_graph_schema(
            driver,
            settings.neo4j_database,
            query_timeout_seconds=settings.neo4j_query_timeout_seconds,
        )
        await seed_graph_memory(
            Neo4jGraphMemoryRepository(
                driver,
                settings.neo4j_database,
                query_timeout_seconds=settings.neo4j_query_timeout_seconds,
            )
        )
    finally:
        await driver.close()


def main() -> None:
    profile = get_settings().runtime_profile
    if profile not in DEVELOPMENT_RUNTIME_PROFILES:
        return
    seed_database(runtime_profile=profile)
    asyncio.run(seed_memory())
    asyncio.run(seed_graph())


if __name__ == "__main__":
    main()
