from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.dispatch import Dispatch
from app.models.order import Order
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
        item["name"] == "ix_dispatch_tasks_assignee_created_at"
        and item["column_names"] == ["assignee_subject_id", "created_at"]
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
