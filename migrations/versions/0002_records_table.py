"""records table

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id"),
            nullable=False,
        ),
        sa.Column(
            "raw_evidence_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_evidence.id"),
            nullable=False,
        ),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("record_type", sa.Text(), nullable=True),
        sa.Column("field_name", sa.Text(), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("actor", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_records_tenant_id", "records", ["tenant_id"])
    op.create_index("ix_records_analysis_id", "records", ["analysis_id"])
    op.create_index("ix_records_raw_evidence_id", "records", ["raw_evidence_id"])
    op.create_index(
        "ix_records_tenant_analysis_source", "records", ["tenant_id", "analysis_id", "source_id"]
    )

    # Align existing timestamp columns with the models, which declare them
    # non-optional; the 0001 migration left them nullable by oversight.
    op.alter_column("tenants", "created_at", existing_type=sa.DateTime(), nullable=False)
    op.alter_column("analyses", "created_at", existing_type=sa.DateTime(), nullable=False)
    op.alter_column(
        "raw_evidence", "fetched_or_uploaded_at", existing_type=sa.DateTime(), nullable=False
    )


def downgrade() -> None:
    op.alter_column(
        "raw_evidence", "fetched_or_uploaded_at", existing_type=sa.DateTime(), nullable=True
    )
    op.alter_column("analyses", "created_at", existing_type=sa.DateTime(), nullable=True)
    op.alter_column("tenants", "created_at", existing_type=sa.DateTime(), nullable=True)
    op.drop_table("records")
