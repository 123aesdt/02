from sqlalchemy import select

from app.models.demo_employee_account import DemoEmployeeAccount
from app.seed import seed_demo_employee_accounts


def test_demo_employee_seed_creates_delivery_and_dispatch_roles_and_preserves_disabled_accounts(sqlite_factory) -> None:
    with sqlite_factory() as session:
        seed_demo_employee_accounts(session)
        session.commit()

        accounts = session.scalars(
            select(DemoEmployeeAccount).order_by(DemoEmployeeAccount.employee_id)
        ).all()
        assert [(item.employee_id, item.display_name, item.role) for item in accounts] == [
            ("CF-DEMO-001", "张师傅", "EMPLOYEE"),
            ("CF-DEMO-002", "李运营", "OPERATOR"),
            ("CF-DEMO-003", "王主管", "SUPERVISOR"),
            ("CF-DEMO-004", "赵审计", "AUDITOR"),
            ("CF-DEMO-005", "系统管理员", "ADMIN"),
            ("CF-DEMO-006", "陈师傅", "EMPLOYEE"),
            ("CF-DEMO-007", "孙调度", "DISPATCHER"),
        ]

        accounts[0].is_active = False
        session.commit()
        seed_demo_employee_accounts(session)
        session.commit()

        repeated = session.scalars(
            select(DemoEmployeeAccount).order_by(DemoEmployeeAccount.employee_id)
        ).all()
        assert len(repeated) == 7
        assert repeated[0].is_active is False
