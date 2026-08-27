"""add slide layout_mode and layout_tree

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-07 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "slides",
        sa.Column(
            "layout_mode",
            sa.String(length=16),
            server_default="fixed",
            nullable=False,
        ),
    )
    op.add_column(
        "slides",
        sa.Column(
            "layout_tree",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("slides", "layout_tree")
    op.drop_column("slides", "layout_mode")
