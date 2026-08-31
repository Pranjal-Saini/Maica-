"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="OPEN"),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_analyses_tenant_id", "analyses", ["tenant_id"])

    op.create_table(
        "raw_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id"),
            nullable=False,
        ),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("fetched_or_uploaded_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("request_made", postgresql.JSONB(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("understood_summary", postgresql.JSONB(), nullable=False),
        sa.Column("unavailable_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_raw_evidence_tenant_id", "raw_evidence", ["tenant_id"])
    op.create_index("ix_raw_evidence_analysis_id", "raw_evidence", ["analysis_id"])
    op.create_index("ix_raw_evidence_tenant_analysis", "raw_evidence", ["tenant_id", "analysis_id"])


def downgrade() -> None:
    op.drop_table("raw_evidence")
    op.drop_table("analyses")
    op.drop_table("tenants")
