"""add driver anomaly report provenance"""

import sqlalchemy as sa

from alembic import op

revision = "20260901_11"
down_revision = "20260830_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("anomalies") as batch:
        batch.add_column(sa.Column("reported_by_subject_id", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("source_task_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("location_text", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("reported_vehicle_status", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("report_idempotency_key", sa.String(length=128), nullable=True))
        batch.create_index("ix_anomalies_reported_by_subject_id", ["reported_by_subject_id"], unique=False)
        batch.create_index("ix_anomalies_source_task_id", ["source_task_id"], unique=False)
        batch.create_unique_constraint("uq_anomalies_report_idempotency_key", ["report_idempotency_key"])


def downgrade() -> None:
    with op.batch_alter_table("anomalies") as batch:
        batch.drop_constraint("uq_anomalies_report_idempotency_key", type_="unique")
        batch.drop_index("ix_anomalies_source_task_id")
        batch.drop_index("ix_anomalies_reported_by_subject_id")
        batch.drop_column("report_idempotency_key")
        batch.drop_column("reported_vehicle_status")
        batch.drop_column("location_text")
        batch.drop_column("source_task_id")
        batch.drop_column("reported_by_subject_id")
