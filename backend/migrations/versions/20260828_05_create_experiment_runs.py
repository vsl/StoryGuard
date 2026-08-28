"""Create experiment runs.

Revision ID: 20260828_05
Revises: 20260824_04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260828_05"
down_revision: str | None = "20260824_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "experiment_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("baseline_config_id", sa.String(length=64), nullable=False),
        sa.Column("candidate_config_id", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="queued", nullable=False
        ),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("completed_units", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_units", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("active_slot", sa.Integer(), nullable=True),
        sa.Column("config_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=True),
        sa.Column("failures", postgresql.JSONB(), nullable=True),
        sa.Column("observability", postgresql.JSONB(), nullable=True),
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
        sa.CheckConstraint("attempts >= 0", name="ck_experiment_run_attempts"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'scoring', 'completed', 'failed')",
            name="ck_experiment_run_status",
        ),
        sa.CheckConstraint(
            "(status IN ('queued', 'running', 'scoring') AND active_slot = 1) "
            "OR (status IN ('completed', 'failed') AND active_slot IS NULL)",
            name="ck_experiment_run_active_slot",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("active_slot"),
    )


def downgrade() -> None:
    op.drop_table("experiment_runs")
