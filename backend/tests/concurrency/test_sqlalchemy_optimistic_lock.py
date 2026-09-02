from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from app.models.base import Base
from app.models.dispatch import Dispatch
from app.models.order import Order


def test_two_independent_sessions_raise_stale_data_error_without_manual_version_check():
    with TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        engine = create_engine(f"sqlite+pysqlite:///{Path(temp_dir) / 'phase1-lock.db'}")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory() as seed:
            order = Order(order_no="ORD-LOCK", status="open", origin="A", destination="B")
            seed.add(order)
            seed.flush()
            seed.add(Dispatch(dispatch_no="DSP-LOCK", order_id=order.id, target_route_id="R-1", status="proposed"))
            seed.commit()
        session_a = factory()
        session_b = factory()
        try:
            dispatch_a = session_a.scalar(select(Dispatch).where(Dispatch.dispatch_no == "DSP-LOCK"))
            dispatch_b = session_b.scalar(select(Dispatch).where(Dispatch.dispatch_no == "DSP-LOCK"))
            assert dispatch_a.version == dispatch_b.version == 1
            dispatch_a.target_route_id = "R-A"
            session_a.commit()
            assert dispatch_a.version == 2
            dispatch_b.target_route_id = "R-B"
            with pytest.raises(StaleDataError):
                session_b.commit()
            session_b.rollback()
        finally:
            session_a.close()
            session_b.close()
        with Session(engine) as verify:
            final = verify.scalar(select(Dispatch).where(Dispatch.dispatch_no == "DSP-LOCK"))
            assert final.target_route_id == "R-A"
            assert final.version == 2
        engine.dispose()
