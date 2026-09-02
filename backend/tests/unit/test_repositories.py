import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.errors import OptimisticLockConflict
from app.models.base import Base
from app.models.dispatch import Dispatch
from app.models.order import Order
from app.repositories.dispatch import DispatchRepository


def test_dispatch_repository_converts_stale_data_error_to_domain_conflict():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        order = Order(order_no="ORD-REPO", status="open", origin="A", destination="B")
        session.add(order)
        session.flush()
        dispatch = Dispatch(dispatch_no="DSP-REPO", order_id=order.id, status="proposed")
        session.add(dispatch)
        session.commit()
        dispatch_id = dispatch.id

    first = factory()
    second = factory()
    try:
        first_dispatch = first.get(Dispatch, dispatch_id)
        second_dispatch = second.get(Dispatch, dispatch_id)
        first_dispatch.status = "assigned"
        first.commit()
        second_dispatch.status = "cancelled"
        with pytest.raises(OptimisticLockConflict):
            DispatchRepository(second).commit_dispatch(second_dispatch)
    finally:
        first.close()
        second.close()
