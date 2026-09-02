from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError

from app.models.shared_memory import SharedMemoryFact
from tests.shared_memory.factories import fact_row


def test_memory_fact_optimistic_lock(sqlite_factory) -> None:
    with sqlite_factory() as seed:
        seed.add(fact_row(confidence=Decimal("0.9000")))
        seed.commit()

    session_a = sqlite_factory()
    session_b = sqlite_factory()
    try:
        fact_a = session_a.scalar(select(SharedMemoryFact).where(SharedMemoryFact.fact_key == "smf_example"))
        fact_b = session_b.scalar(select(SharedMemoryFact).where(SharedMemoryFact.fact_key == "smf_example"))
        fact_a.confidence = Decimal("0.9100")
        session_a.commit()
        fact_b.confidence = Decimal("0.9200")
        with pytest.raises(StaleDataError):
            session_b.commit()
        session_b.rollback()
    finally:
        session_a.close()
        session_b.close()

    with sqlite_factory() as verify:
        fact = verify.scalar(select(SharedMemoryFact).where(SharedMemoryFact.fact_key == "smf_example"))
        assert (fact.confidence, fact.version) == (Decimal("0.9100"), 2)
