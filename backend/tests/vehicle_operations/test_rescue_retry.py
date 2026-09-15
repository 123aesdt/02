from datetime import timedelta

from sqlalchemy import select

from app.models.vehicle_operation import RescueMission, RescueUnit
from app.vehicle_operations.sqlalchemy_repository import SqlAlchemyVehicleOperationsRepository
from tests.vehicle_operations.test_lifecycle_repository import NOW, _request, _seed


def test_failed_rescue_can_be_retried_without_creating_a_duplicate_mission(sqlite_factory):
    _seed(sqlite_factory)
    repository = SqlAlchemyVehicleOperationsRepository(sqlite_factory)
    created = repository.create_breakdown_case(_request())
    with sqlite_factory() as session:
        mission = session.scalar(select(RescueMission).where(RescueMission.mission_no == created.mission.mission_no))
        unit = session.scalar(select(RescueUnit).where(RescueUnit.unit_id == "RU-001"))
        mission.status = "FAILED"
        mission.failure_reason = "道路临时封闭"
        mission.next_transition_at = None
        unit.status = "AVAILABLE"
        session.commit()

    retried = repository.retry_rescue(created.mission.mission_no, NOW + timedelta(minutes=1))

    assert retried.mission.mission_no == created.mission.mission_no
    assert retried.mission.status == "DISPATCHED"
    assert retried.mission.next_transition_at == NOW + timedelta(minutes=1, seconds=8)
