"""add runtime override control and attempt ledgers"""

import sqlalchemy as sa

from alembic import op

revision = "20260827_05"
down_revision = "20260827_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())
    if "runtime_overrides" not in existing_tables:
        op.create_table(
            "runtime_overrides",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("override_id", sa.String(36), nullable=False),
            sa.Column("thread_id", sa.String(96), sa.ForeignKey("runtime_threads.thread_id", ondelete="RESTRICT"), nullable=False),
            sa.Column("task_id", sa.String(36), nullable=False),
            sa.Column("operator_id", sa.String(128), nullable=False),
            sa.Column("operator_role", sa.String(64), nullable=False),
            sa.Column("idempotency_key", sa.String(128), nullable=False),
            sa.Column("payload_fingerprint", sa.String(64), nullable=False),
            sa.Column("expected_version", sa.BigInteger(), nullable=False),
            sa.Column("expected_next_node", sa.String(32)),
            sa.Column("before_state_version", sa.BigInteger()),
            sa.Column("after_state_version", sa.BigInteger()),
            sa.Column("entity_type", sa.String(32), nullable=False),
            sa.Column("entity_id", sa.String(128), nullable=False),
            sa.Column("field_name", sa.String(64), nullable=False),
            sa.Column("old_value_json", sa.JSON(), nullable=False),
            sa.Column("new_value_json", sa.JSON(), nullable=False),
            sa.Column("reason", sa.String(512), nullable=False),
            sa.Column("decision", sa.String(32)),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("source_checkpoint_id", sa.String(64)),
            sa.Column("result_checkpoint_id", sa.String(64)),
            sa.Column("event_status", sa.String(16), nullable=False, server_default="PENDING"),
            sa.Column("intent_expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("error_code", sa.String(64)),
            sa.Column("error_summary", sa.String(512)),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("override_id", name="uq_runtime_overrides_override_id"),
            sa.UniqueConstraint("idempotency_key", name="uq_runtime_overrides_idempotency_key"),
        )
        op.create_index("ix_runtime_overrides_thread_status_expiry", "runtime_overrides", ["thread_id", "status", "intent_expires_at"])
        op.create_index("ix_runtime_overrides_thread_requested", "runtime_overrides", ["thread_id", "requested_at"])
        op.create_index("ix_runtime_overrides_result_checkpoint", "runtime_overrides", ["result_checkpoint_id"])

    if "runtime_override_attempts" not in existing_tables:
        op.create_table(
            "runtime_override_attempts",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("attempt_id", sa.String(36), nullable=False),
            sa.Column("override_id", sa.String(36), sa.ForeignKey("runtime_overrides.override_id", ondelete="RESTRICT"), nullable=False),
            sa.Column("attempt_no", sa.Integer(), nullable=False),
            sa.Column("operation", sa.String(16), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("observed_state_version", sa.BigInteger()),
            sa.Column("source_checkpoint_id", sa.String(64)),
            sa.Column("result_checkpoint_id", sa.String(64)),
            sa.Column("error_code", sa.String(64)),
            sa.Column("error_summary", sa.String(512)),
            sa.Column("authorization_ms", sa.Numeric(12, 3)),
            sa.Column("lock_ms", sa.Numeric(12, 3)),
            sa.Column("checkpoint_read_ms", sa.Numeric(12, 3)),
            sa.Column("state_update_ms", sa.Numeric(12, 3)),
            sa.Column("promotion_ms", sa.Numeric(12, 3)),
            sa.Column("total_ms", sa.Numeric(12, 3)),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("attempt_id", name="uq_runtime_override_attempts_attempt_id"),
            sa.UniqueConstraint("override_id", "attempt_no", name="uq_runtime_override_attempts_override_attempt"),
        )
        op.create_index("ix_runtime_override_attempts_override_created", "runtime_override_attempts", ["override_id", "created_at"])


def downgrade() -> None:
    op.drop_table("runtime_override_attempts")
    op.drop_table("runtime_overrides")
