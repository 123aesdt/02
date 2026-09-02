"""separate delivery employees from dispatch staff"""

import sqlalchemy as sa

from alembic import op

revision = "20260830_10"
down_revision = "20260830_09"
branch_labels = None
depends_on = None

ROLE_CONSTRAINT = "role IN ('EMPLOYEE', 'DISPATCHER', 'OPERATOR', 'SUPERVISOR', 'AUDITOR', 'ADMIN')"
LEGACY_ROLE_CONSTRAINT = "role IN ('DISPATCHER', 'OPERATOR', 'SUPERVISOR', 'AUDITOR', 'ADMIN')"


def _replace_role_constraint(expression: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("demo_employee_accounts") as batch:
            batch.drop_constraint("ck_demo_employee_accounts_role", type_="check")
            batch.create_check_constraint("ck_demo_employee_accounts_role", expression)
        return
    op.drop_constraint(
        "ck_demo_employee_accounts_role",
        "demo_employee_accounts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_demo_employee_accounts_role",
        "demo_employee_accounts",
        expression,
    )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "demo_employee_accounts" not in set(inspector.get_table_names()):
        return
    _replace_role_constraint(ROLE_CONSTRAINT)
    op.execute(
        sa.text(
            "UPDATE demo_employee_accounts "
            "SET role = 'EMPLOYEE', display_name = CASE employee_id "
            "WHEN 'CF-DEMO-001' THEN '张师傅' "
            "WHEN 'CF-DEMO-006' THEN '陈师傅' "
            "ELSE display_name END "
            "WHERE employee_id IN ('CF-DEMO-001', 'CF-DEMO-006')"
        )
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "demo_employee_accounts" not in set(inspector.get_table_names()):
        return
    op.execute(
        sa.text(
            "UPDATE demo_employee_accounts "
            "SET role = 'DISPATCHER', display_name = CASE employee_id "
            "WHEN 'CF-DEMO-001' THEN '张调度' "
            "WHEN 'CF-DEMO-006' THEN '陈调度' "
            "ELSE display_name END "
            "WHERE role = 'EMPLOYEE'"
        )
    )
    _replace_role_constraint(LEGACY_ROLE_CONSTRAINT)
