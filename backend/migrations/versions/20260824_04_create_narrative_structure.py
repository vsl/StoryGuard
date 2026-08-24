"""Create parsed narrative structure.

Revision ID: 20260824_04
Revises: 20260822_03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260824_04"
down_revision: str | None = "20260822_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "manuscript_versions", sa.Column("parse_metadata", sa.JSON(), nullable=True)
    )
    op.create_table(
        "chapters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("manuscript_version_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.CheckConstraint("ordinal > 0", name="ck_chapter_ordinal"),
        sa.ForeignKeyConstraint(
            ["manuscript_version_id"], ["manuscript_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("manuscript_version_id", "ordinal"),
    )
    op.create_index("ix_chapters_manuscript_version_id", "chapters", ["manuscript_version_id"])
    op.create_table(
        "scenes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chapter_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.CheckConstraint("ordinal > 0", name="ck_scene_ordinal"),
        sa.CheckConstraint(
            "start_offset >= 0 AND end_offset > start_offset", name="ck_scene_offsets"
        ),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chapter_id", "ordinal"),
    )
    op.create_index("ix_scenes_chapter_id", "scenes", ["chapter_id"])
    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("manuscript_version_id", sa.Uuid(), nullable=False),
        sa.Column("chapter_id", sa.Uuid(), nullable=False),
        sa.Column("scene_id", sa.Uuid(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_version", sa.String(length=32), nullable=True),
        sa.CheckConstraint("ordinal > 0", name="ck_chunk_ordinal"),
        sa.CheckConstraint(
            "start_offset >= 0 AND end_offset > start_offset", name="ck_chunk_offsets"
        ),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["manuscript_version_id"], ["manuscript_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("manuscript_version_id", "ordinal"),
    )
    op.create_index("ix_chunks_manuscript_version_id", "chunks", ["manuscript_version_id"])
    op.create_index("ix_chunks_chapter_id", "chunks", ["chapter_id"])
    op.create_index("ix_chunks_scene_id", "chunks", ["scene_id"])


def downgrade() -> None:
    op.drop_table("chunks")
    op.drop_table("scenes")
    op.drop_table("chapters")
    op.drop_column("manuscript_versions", "parse_metadata")
