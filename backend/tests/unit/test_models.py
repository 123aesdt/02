from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.dispatch import Dispatch
from app.models.dispatch_evidence import DispatchEvidence
from app.models.fleet_driver import FleetDriver
from app.models.fleet_vehicle import FleetVehicle
from app.models.order import Order
from app.models.road import RoadEdge, RoadNode
from app.models.station import LogisticsStation
from app.models.task import DispatchTask


def test_core_schema_has_business_uniques_foreign_keys_and_version():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    assert any(item["name"] == "uq_orders_order_no" for item in inspector.get_unique_constraints("orders"))
    assert any(item["name"] == "uq_dispatches_dispatch_no" for item in inspector.get_unique_constraints("dispatches"))
    assert "version" in {column["name"] for column in inspector.get_columns("dispatches")}
    assert inspector.get_foreign_keys("dispatches")
    assert "assignee_subject_id" in {column["name"] for column in inspector.get_columns("dispatch_tasks")}
    assert any(
        item["name"] == "ix_dispatch_tasks_assignee_created_at" and item["column_names"] == ["assignee_subject_id", "created_at"]
        for item in inspector.get_indexes("dispatch_tasks")
    )


def test_dispatch_version_is_assigned_by_sqlalchemy_not_application_check():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        order = Order(order_no="ORD-001", status="open", origin="A", destination="B")
        session.add(order)
        session.flush()
        dispatch = Dispatch(dispatch_no="DSP-001", order_id=order.id, status="proposed")
        session.add(dispatch)
        session.commit()
        assert dispatch.version == 1


def test_dispatch_task_persists_employee_subject_assignment():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        order = Order(order_no="ORD-ASSIGNED", status="IN_TRANSIT", origin="A", destination="B")
        session.add(order)
        session.flush()
        task = DispatchTask(
            task_id="TASK-ASSIGNED",
            order_id=order.id,
            status="APPROVED",
            idempotency_key="assigned-task",
            assignee_subject_id="CF-DEMO-001",
        )
        session.add(task)
        session.commit()

        assert task.assignee_subject_id == "CF-DEMO-001"


def test_offline_fleet_schema_registers_operational_tables_and_constraints():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    assert {
        "logistics_stations",
        "fleet_drivers",
        "fleet_vehicles",
        "road_nodes",
        "road_edges",
        "dispatch_evidence",
    } <= set(inspector.get_table_names())
    assert any(item["name"] == "uq_fleet_vehicles_vehicle_id" for item in inspector.get_unique_constraints("fleet_vehicles"))
    assert any(
        item["name"] == "ix_fleet_vehicles_status_node" and item["column_names"] == ["status", "current_node_id"]
        for item in inspector.get_indexes("fleet_vehicles")
    )
    assert FleetVehicle.__mapper__.version_id_col is FleetVehicle.__table__.c.version
    assert RoadEdge.__mapper__.version_id_col is RoadEdge.__table__.c.version
    assert next(iter(DispatchEvidence.__table__.c.dispatch_id.foreign_keys)).ondelete == "CASCADE"
    assert LogisticsStation.__table__.name == "logistics_stations"
    assert FleetDriver.__table__.name == "fleet_drivers"
    assert RoadNode.__table__.name == "road_nodes"
