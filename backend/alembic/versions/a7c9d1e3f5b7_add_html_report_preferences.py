"""add HTML report preferences to projects

Revision ID: a7c9d1e3f5b7
Revises: f6a7b8c9d0e1
Create Date: 2026-09-01 08:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a7c9d1e3f5b7"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("output_format", sa.String(length=16), server_default="ppt", nullable=False),
    )
    op.add_column("projects", sa.Column("html_style_prompt", sa.Text(), nullable=True))
    op.add_column(
        "projects",
        sa.Column(
            "html_style",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "html_style")
    op.drop_column("projects", "html_style_prompt")
    op.drop_column("projects", "output_format")
