"""Create manuscript versions and current-version pointer.

Revision ID: 20260822_02
Revises: 20260822_01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_02"
down_revision: str | None = "20260822_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "manuscript_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="uploaded", nullable=False
        ),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "pipeline_version",
            sa.String(length=32),
            server_default="v1",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("file_size > 0", name="ck_manuscript_file_size"),
        sa.CheckConstraint(
            "status IN ('uploaded', 'processing', 'ready', 'failed', 'archived')",
            name="ck_manuscript_status",
        ),
        sa.CheckConstraint("version_number > 0", name="ck_manuscript_version_number"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
        sa.UniqueConstraint("project_id", "version_number"),
    )
    op.create_index(
        "ix_manuscript_versions_project_id", "manuscript_versions", ["project_id"]
    )
    op.add_column(
        "projects",
        sa.Column("current_manuscript_version_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_projects_current_manuscript_version_id",
        "projects",
        "manuscript_versions",
        ["current_manuscript_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_projects_current_manuscript_version_id", "projects", type_="foreignkey"
    )
    op.drop_column("projects", "current_manuscript_version_id")
    op.drop_index("ix_manuscript_versions_project_id", table_name="manuscript_versions")
    op.drop_table("manuscript_versions")
