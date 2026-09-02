"""persist AI review recommendations and action-only publications"""

import sqlalchemy as sa

from alembic import op

revision = "20260901_12"
down_revision = "20260901_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("dispatches") as batch:
        batch.add_column(sa.Column("recommended_action", sa.Text(), nullable=True))
        batch.add_column(sa.Column("analysis_mode", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("issue_subtype", sa.String(length=32), nullable=True))
    with op.batch_alter_table("dispatch_publications") as batch:
        batch.alter_column(
            "route_id",
            existing_type=sa.String(length=64),
            existing_nullable=False,
            nullable=True,
        )
        batch.alter_column(
            "route_instruction",
            existing_type=sa.Text(),
            existing_nullable=False,
            nullable=True,
        )
        batch.add_column(sa.Column("action_instruction", sa.Text(), nullable=True))


def downgrade() -> None:
    publications = sa.table(
        "dispatch_publications",
        sa.column("route_id", sa.String(length=64)),
        sa.column("route_instruction", sa.Text()),
    )
    op.execute(publications.update().where(publications.c.route_id.is_(None)).values(route_id="UNAVAILABLE"))
    op.execute(
        publications.update()
        .where(publications.c.route_instruction.is_(None))
        .values(route_instruction="Action-only instruction was removed by migration downgrade.")
    )
    with op.batch_alter_table("dispatch_publications") as batch:
        batch.drop_column("action_instruction")
        batch.alter_column(
            "route_instruction",
            existing_type=sa.Text(),
            existing_nullable=True,
            nullable=False,
        )
        batch.alter_column(
            "route_id",
            existing_type=sa.String(length=64),
            existing_nullable=True,
            nullable=False,
        )
    with op.batch_alter_table("dispatches") as batch:
        batch.drop_column("issue_subtype")
        batch.drop_column("analysis_mode")
        batch.drop_column("recommended_action")
