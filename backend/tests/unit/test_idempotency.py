from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.idempotency.service import IdempotencyConflictError, IdempotencyService
from app.models.base import Base
from app.models.order import Order
from app.models.task import DispatchTask


def _service() -> tuple[TemporaryDirectory, object, sessionmaker]:
    temp = TemporaryDirectory()
    engine = create_engine(f"sqlite+pysqlite:///{Path(temp.name) / 'idempotency.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(Order(order_no="ORD-IDEMPOTENCY", status="open", origin="A", destination="B"))
        session.commit()
    return temp, engine, factory


def test_idempotency_first_execution_is_new():
    temp, engine, factory = _service()
    try:
        decision = IdempotencyService(factory).begin("task-001", 1, "idem-001")

        assert (decision.state, decision.task_id, decision.idempotency_key, decision.should_execute) == (
            "NEW",
            "task-001",
            "idem-001",
            True,
        )
    finally:
        engine.dispose()
        temp.cleanup()


def test_idempotency_same_task_is_replay():
    temp, engine, factory = _service()
    try:
        service = IdempotencyService(factory)
        service.begin("task-001", 1, "idem-001")

        decision = service.begin("task-001", 1, "idem-001")
        with factory() as session:
            task_count = session.scalar(select(func.count()).select_from(DispatchTask))

        assert (decision.state, decision.should_execute, task_count) == ("IN_PROGRESS", False, 1)
    finally:
        engine.dispose()
        temp.cleanup()


def test_idempotency_terminal_task_is_detected():
    temp, engine, factory = _service()
    try:
        service = IdempotencyService(factory)
        service.begin("task-001", 1, "idem-001")
        service.mark_terminal("task-001", "COMPLETED")

        decision = service.begin("task-001", 1, "idem-001")

        assert (decision.state, decision.existing_status, decision.should_execute) == ("TERMINAL", "COMPLETED", False)
    finally:
        engine.dispose()
        temp.cleanup()


def test_idempotency_key_cannot_map_to_different_task():
    temp, engine, factory = _service()
    try:
        service = IdempotencyService(factory)
        service.begin("task-001", 1, "idem-001")

        with pytest.raises(IdempotencyConflictError):
            service.begin("task-999", 1, "idem-001")
    finally:
        engine.dispose()
        temp.cleanup()


def test_concurrent_same_idempotency_key_creates_single_ledger():
    temp, engine, factory = _service()
    try:
        session_a = factory()
        session_b = factory()
        try:
            session_a.add(DispatchTask(task_id="task-001", order_id=1, status="PENDING", idempotency_key="idem-001"))
            session_a.commit()
            session_b.add(DispatchTask(task_id="task-002", order_id=1, status="PENDING", idempotency_key="idem-001"))
            with pytest.raises(IntegrityError):
                session_b.commit()
            session_b.rollback()
        finally:
            session_a.close()
            session_b.close()

        with factory() as session:
            task_count = session.scalar(select(func.count()).select_from(DispatchTask))
        assert task_count == 1
    finally:
        engine.dispose()
        temp.cleanup()
