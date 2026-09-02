"""add compact graph memory audit evidence"""

import sqlalchemy as sa

from alembic import op

revision = "20260826_02"
down_revision = "20260821_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_records", sa.Column("evidence_json", sa.Text(), nullable=True))
    op.execute("UPDATE audit_records SET evidence_json = '{}' WHERE evidence_json IS NULL")
    op.alter_column("audit_records", "evidence_json", existing_type=sa.Text(), nullable=False)


def downgrade() -> None:
    op.drop_column("audit_records", "evidence_json")
