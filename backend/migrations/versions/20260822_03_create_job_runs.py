"""Create job runs.

Revision ID: 20260822_03
Revises: 20260822_02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_03"
down_revision: str | None = "20260822_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("manuscript_version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status", sa.String(length=16), server_default="queued", nullable=False
        ),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("completed_units", sa.Integer(), nullable=True),
        sa.Column("total_units", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message_safe", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempts >= 0", name="ck_job_run_attempts"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_job_run_status",
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_version_id"],
            ["manuscript_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_job_runs_project_id", "job_runs", ["project_id"])
    op.create_index(
        "ix_job_runs_manuscript_version_id", "job_runs", ["manuscript_version_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_job_runs_manuscript_version_id", table_name="job_runs")
    op.drop_index("ix_job_runs_project_id", table_name="job_runs")
    op.drop_table("job_runs")
