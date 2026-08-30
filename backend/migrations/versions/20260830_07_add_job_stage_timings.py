"""Store ingestion stage timings.

Revision ID: 20260830_07
Revises: 20260828_06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260830_07"
down_revision: str | None = "20260828_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("job_runs", sa.Column("stage_started_at", sa.DateTime(timezone=True)))
    op.add_column(
        "job_runs",
        sa.Column(
            "stage_durations_ms",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("job_runs", "stage_durations_ms")
    op.drop_column("job_runs", "stage_started_at")
