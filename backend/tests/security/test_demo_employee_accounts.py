import pytest

from app.models.demo_employee_account import DemoEmployeeAccount
from app.security.demo_employee_accounts import (
    DemoEmployeeNotFound,
    DemoEmployeeSessionService,
    SqlAlchemyDemoEmployeeAccountRepository,
)
from app.security.development_session import DevelopmentSessionIssuer
from app.security.permissions import Permission, Role
from app.seed import seed_demo_employee_accounts


def build_service(sqlite_factory) -> DemoEmployeeSessionService:
    with sqlite_factory() as session:
        seed_demo_employee_accounts(session)
        session.commit()
    repository = SqlAlchemyDemoEmployeeAccountRepository(sqlite_factory)
    issuer = DevelopmentSessionIssuer(
        "demo-employee-session-secret-value",
        issuer="countyflow-dev",
        audience="countyflow-api",
        ttl_seconds=600,
    )
    return DemoEmployeeSessionService(repository, issuer)


def test_lists_only_active_demo_employees_in_stable_order(sqlite_factory) -> None:
    service = build_service(sqlite_factory)
    with sqlite_factory() as session:
        account = session.get(DemoEmployeeAccount, "CF-DEMO-002")
        assert account is not None
        account.is_active = False
        session.commit()

    accounts = service.list_accounts()

    assert [item.employee_id for item in accounts] == [
        "CF-DEMO-001",
        "CF-DEMO-003",
        "CF-DEMO-004",
        "CF-DEMO-005",
        "CF-DEMO-006",
        "CF-DEMO-007",
    ]


def test_issue_normalizes_employee_id_and_uses_repository_role(sqlite_factory) -> None:
    service = build_service(sqlite_factory)

    issued = service.issue("  cf-demo-001  ")

    assert issued.principal.subject_id == "CF-DEMO-001"
    assert issued.principal.display_name == "张师傅"
    assert issued.principal.roles == frozenset({Role.EMPLOYEE})
    assert Permission.DISPATCH_CREATE not in issued.principal.permissions


def test_unknown_demo_employee_cannot_receive_session(sqlite_factory) -> None:
    service = build_service(sqlite_factory)

    with pytest.raises(DemoEmployeeNotFound):
        service.issue("CF-DEMO-999")
