"""add authenticated employee assignment to dispatch tasks"""

import sqlalchemy as sa

from alembic import op

revision = "20260830_08"
down_revision = "20260830_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("dispatch_tasks")}
    if "assignee_subject_id" not in columns:
        op.add_column(
            "dispatch_tasks",
            sa.Column("assignee_subject_id", sa.String(128), nullable=True),
        )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("dispatch_tasks")}
    if "ix_dispatch_tasks_assignee_created_at" not in indexes:
        op.create_index(
            "ix_dispatch_tasks_assignee_created_at",
            "dispatch_tasks",
            ["assignee_subject_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("dispatch_tasks")}
    if "ix_dispatch_tasks_assignee_created_at" in indexes:
        op.drop_index("ix_dispatch_tasks_assignee_created_at", table_name="dispatch_tasks")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("dispatch_tasks")}
    if "assignee_subject_id" in columns:
        op.drop_column("dispatch_tasks", "assignee_subject_id")
