"""add passwordless demo employee accounts"""

import sqlalchemy as sa

from alembic import op

revision = "20260830_07"
down_revision = "20260828_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "demo_employee_accounts" in set(sa.inspect(bind).get_table_names()):
        return
    op.create_table(
        "demo_employee_accounts",
        sa.Column("employee_id", sa.String(32), primary_key=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('DISPATCHER', 'OPERATOR', 'SUPERVISOR', 'AUDITOR', 'ADMIN')",
            name="ck_demo_employee_accounts_role",
        ),
    )


def downgrade() -> None:
    op.drop_table("demo_employee_accounts")
