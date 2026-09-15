from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.vehicle_operation import MaintenanceBay, RescueUnit


def seed_vehicle_operation_resources(session: Session) -> None:
    unit = session.scalar(select(RescueUnit).where(RescueUnit.unit_id == "RU-001"))
    if unit is None:
        session.add(
            RescueUnit(
                unit_id="RU-001",
                name="新平县道路救援-02",
                plate_no="新救援-02",
                unit_type="TOW_TRUCK",
                status="AVAILABLE",
                current_node_id="N15",
                capacity_tons=Decimal("8.00"),
            )
        )
    bay = session.scalar(select(MaintenanceBay).where(MaintenanceBay.bay_code == "A-02"))
    if bay is None:
        session.add(
            MaintenanceBay(
                bay_code="A-02",
                station_id="ST-007",
                status="AVAILABLE",
                current_order_no=None,
            )
        )
