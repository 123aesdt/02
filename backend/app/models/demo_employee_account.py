from sqlalchemy import Boolean, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DemoEmployeeAccount(TimestampMixin, Base):
    __tablename__ = "demo_employee_accounts"
    __table_args__ = (
        CheckConstraint(
            "role IN ('EMPLOYEE', 'DISPATCHER', 'OPERATOR', 'SUPERVISOR', 'AUDITOR', 'ADMIN')",
            name="ck_demo_employee_accounts_role",
        ),
    )

    employee_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
