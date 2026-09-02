"""initial CountyFlow schema"""

import sqlalchemy as sa

from alembic import op

revision = "20260821_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_no", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("driver_id", sa.String(64)),
        sa.Column("vehicle_id", sa.String(64)),
        sa.Column("route_id", sa.String(64)),
        sa.Column("origin", sa.String(255), nullable=False),
        sa.Column("destination", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_no", name="uq_orders_order_no"),
    )
    op.create_table(
        "anomalies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("anomaly_no", sa.String(64), nullable=False),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("anomaly_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("anomaly_no", name="uq_anomalies_anomaly_no"),
    )
    op.create_table(
        "dispatch_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("anomaly_id", sa.Integer(), sa.ForeignKey("anomalies.id", ondelete="RESTRICT")),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", name="uq_dispatch_tasks_task_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_dispatch_tasks_idempotency_key"),
    )
    op.create_table(
        "dispatches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dispatch_no", sa.String(64), nullable=False),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("dispatch_tasks.id", ondelete="RESTRICT")),
        sa.Column("original_driver_id", sa.String(64)),
        sa.Column("target_driver_id", sa.String(64)),
        sa.Column("original_route_id", sa.String(64)),
        sa.Column("target_route_id", sa.String(64)),
        sa.Column("decision_reason", sa.Text()),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("fallback_reason", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dispatch_no", name="uq_dispatches_dispatch_no"),
    )
    op.create_table(
        "audit_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "task_id",
            sa.Integer(),
            sa.ForeignKey("dispatch_tasks.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "dispatch_id",
            sa.Integer(),
            sa.ForeignKey("dispatches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_records")
    op.drop_table("dispatches")
    op.drop_table("dispatch_tasks")
    op.drop_table("anomalies")
    op.drop_table("orders")
