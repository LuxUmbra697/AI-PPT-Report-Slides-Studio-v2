"""add independent HTML report generation state

Revision ID: b8d0e2f4a6c8
Revises: a7c9d1e3f5b7
Create Date: 2026-09-01 10:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b8d0e2f4a6c8"
down_revision: str | Sequence[str] | None = "a7c9d1e3f5b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "html_report_status",
            sa.String(length=16),
            server_default="idle",
            nullable=False,
        ),
    )
    op.add_column("projects", sa.Column("html_report_job_id", sa.String(length=100), nullable=True))
    op.add_column("projects", sa.Column("html_report_error", sa.Text(), nullable=True))
    op.add_column(
        "projects",
        sa.Column(
            "html_report_data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "html_report_data")
    op.drop_column("projects", "html_report_error")
    op.drop_column("projects", "html_report_job_id")
    op.drop_column("projects", "html_report_status")
