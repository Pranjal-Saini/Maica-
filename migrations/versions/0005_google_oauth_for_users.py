"""google oauth for users

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Google Sign-In replaces password auth entirely. Existing users have no
    # google_sub to backfill, and this is pre-launch dev/test data only — see
    # hard-rules.md ("pre-launch until real NetSuite connectivity, security,
    # and end-to-end behaviour are validated") — so clear them rather than
    # inventing a value.
    op.execute("DELETE FROM user_tenant_access")
    op.execute("DELETE FROM users")

    op.drop_column("users", "password_hash")
    op.add_column("users", sa.Column("google_sub", sa.Text(), nullable=False))
    op.add_column("users", sa.Column("name", sa.Text(), nullable=True))
    op.create_unique_constraint("uq_users_google_sub", "users", ["google_sub"])


def downgrade() -> None:
    op.drop_constraint("uq_users_google_sub", "users", type_="unique")
    op.drop_column("users", "name")
    op.drop_column("users", "google_sub")
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=False))
