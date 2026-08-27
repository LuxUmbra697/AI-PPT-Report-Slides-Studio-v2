"""slide layout_mode server_default flex

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-07 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "slides",
        "layout_mode",
        existing_type=sa.String(length=16),
        server_default="flex",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "slides",
        "layout_mode",
        existing_type=sa.String(length=16),
        server_default="fixed",
        existing_nullable=False,
    )
