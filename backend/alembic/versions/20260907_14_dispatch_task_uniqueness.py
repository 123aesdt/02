"""enforce one dispatch per task"""

from alembic import op

revision = "20260907_14"
down_revision = "20260902_13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("dispatches") as batch:
        batch.create_unique_constraint("uq_dispatches_task_id", ["task_id"])


def downgrade() -> None:
    with op.batch_alter_table("dispatches") as batch:
        batch.drop_constraint("uq_dispatches_task_id", type_="unique")