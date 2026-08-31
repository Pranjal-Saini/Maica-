"""users and user tenant access

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "user_tenant_access",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_user_tenant_access"),
    )
    op.create_index("ix_user_tenant_access_user_id", "user_tenant_access", ["user_id"])
    op.create_index("ix_user_tenant_access_tenant_id", "user_tenant_access", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_user_tenant_access_tenant_id", table_name="user_tenant_access")
    op.drop_index("ix_user_tenant_access_user_id", table_name="user_tenant_access")
    op.drop_table("user_tenant_access")
    op.drop_table("users")
