"""Allow cancelled manuscript versions and ingestion jobs."""

from alembic import op

revision = "20260830_10"
down_revision = "20260830_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_job_run_status", "job_runs", type_="check")
    op.create_check_constraint(
        "ck_job_run_status", "job_runs",
        "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
    )
    op.drop_constraint("ck_manuscript_status", "manuscript_versions", type_="check")
    op.create_check_constraint(
        "ck_manuscript_status", "manuscript_versions",
        "status IN ('uploaded', 'processing', 'ready', 'failed', 'archived', 'cancelled')",
    )


def downgrade() -> None:
    # Fail rather than silently discard cancellation history if cancelled rows exist.
    op.drop_constraint("ck_job_run_status", "job_runs", type_="check")
    op.create_check_constraint(
        "ck_job_run_status", "job_runs",
        "status IN ('queued', 'running', 'completed', 'failed')",
    )
    op.drop_constraint("ck_manuscript_status", "manuscript_versions", type_="check")
    op.create_check_constraint(
        "ck_manuscript_status", "manuscript_versions",
        "status IN ('uploaded', 'processing', 'ready', 'failed', 'archived')",
    )
