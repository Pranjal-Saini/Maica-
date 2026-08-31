"""records context column

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("records", sa.Column("context", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("records", "context")
