"""add append-only security audit events"""

import sqlalchemy as sa

from alembic import op

revision = "20260828_06"
down_revision = "20260827_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "security_audit_events" in set(sa.inspect(bind).get_table_names()):
        return
    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(64), nullable=False, unique=True),
        sa.Column("subject_id", sa.String(128)),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("permission", sa.String(64)),
        sa.Column("route_template", sa.String(160), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("remote_ip", sa.String(45)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_security_audit_created", "security_audit_events", ["created_at"])
    op.create_index("ix_security_audit_event_created", "security_audit_events", ["event_type", "created_at"])
    op.create_index("ix_security_audit_subject_created", "security_audit_events", ["subject_id", "created_at"])
    op.create_index("ix_security_audit_request", "security_audit_events", ["request_id"])


def downgrade() -> None:
    op.drop_table("security_audit_events")

