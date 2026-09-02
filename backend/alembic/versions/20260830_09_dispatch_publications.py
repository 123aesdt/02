"""add local dispatch publication records"""

import sqlalchemy as sa

from alembic import op

revision = "20260830_09"
down_revision = "20260830_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "dispatch_publications" in inspector.get_table_names():
        return
    op.create_table(
        "dispatch_publications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("dispatch_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("route_id", sa.String(length=64), nullable=False),
        sa.Column("route_instruction", sa.Text(), nullable=False),
        sa.Column("published_by_subject_id", sa.String(length=128), nullable=False),
        sa.Column("published_by_display_name", sa.String(length=256), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dispatch_id"], ["dispatches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["dispatch_tasks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dispatch_id", name="uq_dispatch_publications_dispatch_id"),
        sa.UniqueConstraint("task_id", name="uq_dispatch_publications_task_id"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if "dispatch_publications" in sa.inspect(bind).get_table_names():
        op.drop_table("dispatch_publications")
