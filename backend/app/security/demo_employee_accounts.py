from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.demo_employee_account import DemoEmployeeAccount
from app.security.development_session import DevelopmentSession, DevelopmentSessionIssuer
from app.security.permissions import Role


@dataclass(frozen=True)
class DemoEmployee:
    employee_id: str
    display_name: str
    role: Role


class DemoEmployeeNotFound(LookupError):
    pass


class DemoEmployeeAccountRepository(Protocol):
    def list_active(self) -> tuple[DemoEmployee, ...]: ...

    def get_active(self, employee_id: str) -> DemoEmployee | None: ...


class SqlAlchemyDemoEmployeeAccountRepository:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def list_active(self) -> tuple[DemoEmployee, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(DemoEmployeeAccount)
                .where(DemoEmployeeAccount.is_active.is_(True))
                .order_by(DemoEmployeeAccount.employee_id)
            ).all()
            return tuple(_to_employee(row) for row in rows)

    def get_active(self, employee_id: str) -> DemoEmployee | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(DemoEmployeeAccount).where(
                    DemoEmployeeAccount.employee_id == employee_id,
                    DemoEmployeeAccount.is_active.is_(True),
                )
            )
            return _to_employee(row) if row is not None else None


class DemoEmployeeSessionService:
    def __init__(
        self,
        repository: DemoEmployeeAccountRepository,
        issuer: DevelopmentSessionIssuer,
    ) -> None:
        self._repository = repository
        self._issuer = issuer

    def list_accounts(self) -> tuple[DemoEmployee, ...]:
        return self._repository.list_active()

    def issue(self, employee_id: str) -> DevelopmentSession:
        normalized = employee_id.strip().upper()
        employee = self._repository.get_active(normalized) if normalized else None
        if employee is None:
            raise DemoEmployeeNotFound
        return self._issuer.issue_identity(
            subject_id=employee.employee_id,
            display_name=employee.display_name,
            role=employee.role,
        )


def _to_employee(account: DemoEmployeeAccount) -> DemoEmployee:
    return DemoEmployee(
        employee_id=account.employee_id,
        display_name=account.display_name,
        role=Role(account.role),
    )
