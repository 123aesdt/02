"""add shared memory mutation control plane"""

import sqlalchemy as sa

from alembic import op

revision = "20260827_03"
down_revision = "20260826_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_mutations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("mutation_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("payload_fingerprint", sa.String(64), nullable=False),
        sa.Column("fact_key", sa.String(68), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("fact_kind", sa.String(32), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("operator_id", sa.String(128), nullable=False),
        sa.Column("expected_version", sa.Integer()),
        sa.Column("incoming_confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("incoming_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("human_confirmed", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(512), nullable=False),
        sa.Column("targets_json", sa.JSON(), nullable=False),
        sa.Column("proposed_fact_json", sa.JSON(), nullable=False),
        sa.Column("decision", sa.String(32)),
        sa.Column("reason_code", sa.String(64)),
        sa.Column("before_version", sa.Integer()),
        sa.Column("after_version", sa.Integer()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("vector_status", sa.String(32), nullable=False),
        sa.Column("graph_status", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_summary", sa.String(512)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("mutation_id", name="uq_memory_mutations_mutation_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_memory_mutations_idempotency_key"),
    )
    op.create_index("ix_memory_mutations_fact_created", "memory_mutations", ["fact_key", "created_at"])
    op.create_index("ix_memory_mutations_status", "memory_mutations", ["status"])
    op.create_index(
        "ix_memory_mutations_projection_status",
        "memory_mutations",
        ["vector_status", "graph_status"],
    )

    op.create_table(
        "shared_memory_facts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("fact_id", sa.String(36), nullable=False),
        sa.Column("fact_key", sa.String(68), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("fact_kind", sa.String(32), nullable=False),
        sa.Column("subject_type", sa.String(64), nullable=False),
        sa.Column("subject_id", sa.String(128), nullable=False),
        sa.Column("predicate", sa.String(64), nullable=False),
        sa.Column("object_type", sa.String(64)),
        sa.Column("object_id", sa.String(128)),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("content_fingerprint", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("vector_memory_id", sa.String(128)),
        sa.Column("graph_fact_key", sa.String(255)),
        sa.Column("last_mutation_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("fact_id", name="uq_shared_memory_facts_fact_id"),
        sa.UniqueConstraint("fact_key", name="uq_shared_memory_facts_fact_key"),
    )
    op.create_index(
        "ix_shared_memory_facts_category_status",
        "shared_memory_facts",
        ["category", "status"],
    )
    op.create_index(
        "ix_shared_memory_facts_subject_predicate",
        "shared_memory_facts",
        ["subject_type", "subject_id", "predicate"],
    )
    op.create_index("ix_shared_memory_facts_expires_at", "shared_memory_facts", ["expires_at"])

    op.create_table(
        "memory_evidence",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("evidence_id", sa.String(36), nullable=False),
        sa.Column(
            "mutation_id",
            sa.String(36),
            sa.ForeignKey("memory_mutations.mutation_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("fact_id", sa.String(36)),
        sa.Column("evidence_fingerprint", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("evidence_text", sa.Text()),
        sa.Column("evidence_ref", sa.String(512)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("safe_summary", sa.String(512)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("evidence_id", name="uq_memory_evidence_evidence_id"),
        sa.UniqueConstraint(
            "mutation_id",
            "evidence_fingerprint",
            name="uq_memory_evidence_mutation_fingerprint",
        ),
    )
    op.create_index("ix_memory_evidence_fact_id", "memory_evidence", ["fact_id"])

    op.create_table(
        "memory_mutation_attempts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("attempt_id", sa.String(36), nullable=False),
        sa.Column(
            "mutation_id",
            sa.String(36),
            sa.ForeignKey("memory_mutations.mutation_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("vector_before", sa.String(32), nullable=False),
        sa.Column("vector_after", sa.String(32), nullable=False),
        sa.Column("graph_before", sa.String(32), nullable=False),
        sa.Column("graph_after", sa.String(32), nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_summary", sa.String(512)),
        sa.UniqueConstraint("attempt_id", name="uq_memory_mutation_attempts_attempt_id"),
        sa.UniqueConstraint(
            "mutation_id",
            "attempt_no",
            name="uq_memory_mutation_attempts_mutation_attempt",
        ),
    )


def downgrade() -> None:
    op.drop_table("memory_mutation_attempts")
    op.drop_index("ix_memory_evidence_fact_id", table_name="memory_evidence")
    op.drop_table("memory_evidence")
    op.drop_index("ix_shared_memory_facts_expires_at", table_name="shared_memory_facts")
    op.drop_index("ix_shared_memory_facts_subject_predicate", table_name="shared_memory_facts")
    op.drop_index("ix_shared_memory_facts_category_status", table_name="shared_memory_facts")
    op.drop_table("shared_memory_facts")
    op.drop_index("ix_memory_mutations_projection_status", table_name="memory_mutations")
    op.drop_index("ix_memory_mutations_status", table_name="memory_mutations")
    op.drop_index("ix_memory_mutations_fact_created", table_name="memory_mutations")
    op.drop_table("memory_mutations")
