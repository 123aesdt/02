"""add persistent runtime thread registry"""

from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision = "20260827_04"
down_revision = "20260827_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())
    if "runtime_threads" not in existing_tables:
        op.create_table(
            "runtime_threads",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("thread_id", sa.String(96), nullable=False),
            sa.Column("task_id", sa.String(36), sa.ForeignKey("dispatch_tasks.task_id", ondelete="RESTRICT"), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("current_checkpoint_id", sa.String(64)),
            sa.Column("state_version", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("current_node", sa.String(32)),
            sa.Column("next_node", sa.String(32)),
            sa.Column("checkpoint_count", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("checkpoint_size_bytes", sa.BigInteger()),
            sa.Column("last_event_sequence", sa.BigInteger()),
            sa.Column("worker_consumer", sa.String(128)),
            sa.Column("resumed_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("terminal_at", sa.DateTime(timezone=True)),
            sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("thread_id", name="uq_runtime_threads_thread_id"),
            sa.UniqueConstraint("task_id", name="uq_runtime_threads_task_id"),
        )
        op.create_index("ix_runtime_threads_status_updated", "runtime_threads", ["status", "updated_at"])
        op.create_index("ix_runtime_threads_current_checkpoint", "runtime_threads", ["current_checkpoint_id"])

    if "runtime_thread_events" not in existing_tables:
        op.create_table(
            "runtime_thread_events",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("event_id", sa.String(36), nullable=False),
            sa.Column("event_key", sa.String(160), nullable=False),
            sa.Column("thread_id", sa.String(96), sa.ForeignKey("runtime_threads.thread_id", ondelete="RESTRICT"), nullable=False),
            sa.Column("event_type", sa.String(32), nullable=False),
            sa.Column("checkpoint_id", sa.String(64)),
            sa.Column("parent_checkpoint_id", sa.String(64)),
            sa.Column("state_version", sa.BigInteger(), nullable=False),
            sa.Column("node", sa.String(32)),
            sa.Column("next_node", sa.String(32)),
            sa.Column("checkpoint_size_bytes", sa.BigInteger()),
            sa.Column("worker_consumer", sa.String(128)),
            sa.Column("error_code", sa.String(64)),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("event_id", name="uq_runtime_thread_events_event_id"),
            sa.UniqueConstraint("thread_id", "event_key", name="uq_runtime_thread_events_thread_event_key"),
        )
        op.create_index("ix_runtime_thread_events_thread_version", "runtime_thread_events", ["thread_id", "state_version"])
        op.create_index("ix_runtime_thread_events_thread_created", "runtime_thread_events", ["thread_id", "created_at"])

    tasks = sa.table(
        "dispatch_tasks",
        sa.column("task_id", sa.String(36)),
        sa.column("status", sa.String(32)),
        sa.column("completed_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    stored_thread_ids = set(bind.execute(sa.text("SELECT task_id FROM runtime_threads")).scalars())
    existing = [row for row in bind.execute(sa.select(tasks)).mappings() if row["task_id"] not in stored_thread_ids]
    if existing:
        thread_rows = []
        for task in existing:
            thread_id = f"cf:dispatch:{task['task_id']}"
            terminal = task["status"] in {"APPROVED", "COMPLETED", "REVIEW_REQUIRED", "DLQ", "FAILED"}
            thread_rows.append(
                {
                    "thread_id": thread_id,
                    "task_id": task["task_id"],
                    "status": "TERMINAL" if terminal else "RUNNING",
                    "next_node": None if terminal else "intake",
                    "state_version": 0,
                    "checkpoint_count": 0,
                    "resumed_count": 0,
                    "terminal_at": task["completed_at"] if terminal else None,
                    "row_version": 1,
                    "created_at": task["created_at"],
                    "updated_at": task["updated_at"],
                }
            )
        runtime_threads = sa.table(
            "runtime_threads",
            *[sa.column(name) for name in thread_rows[0]],
        )
        op.bulk_insert(runtime_threads, thread_rows)

    missing_created_events = list(
        bind.execute(
            sa.text(
                "SELECT t.thread_id, t.created_at FROM runtime_threads t "
                "LEFT JOIN runtime_thread_events e "
                "ON e.thread_id=t.thread_id AND e.event_key='thread:created' "
                "WHERE e.id IS NULL"
            )
        ).mappings()
    )
    if missing_created_events:
        event_rows = [
            {
                "event_id": str(uuid4()),
                "event_key": "thread:created",
                "thread_id": row["thread_id"],
                "event_type": "THREAD_CREATED",
                "state_version": 0,
                "metadata_json": {},
                "created_at": row["created_at"],
            }
            for row in missing_created_events
        ]
        runtime_events = sa.table(
            "runtime_thread_events",
            sa.column("event_id", sa.String(36)),
            sa.column("event_key", sa.String(160)),
            sa.column("thread_id", sa.String(96)),
            sa.column("event_type", sa.String(32)),
            sa.column("state_version", sa.BigInteger()),
            sa.column("metadata_json", sa.JSON()),
            sa.column("created_at", sa.DateTime(timezone=True)),
        )
        op.bulk_insert(runtime_events, event_rows)


def downgrade() -> None:
    op.drop_table("runtime_thread_events")
    op.drop_table("runtime_threads")
