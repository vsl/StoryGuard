"""Create extracted entity mentions.

Revision ID: 20260828_06
Revises: 20260828_05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_06"
down_revision: str | None = "20260828_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "entity_mentions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("manuscript_version_id", sa.Uuid(), nullable=False),
        sa.Column("chapter_id", sa.Uuid(), nullable=False),
        sa.Column("scene_id", sa.Uuid(), nullable=True),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=16), nullable=False),
        sa.Column("surface_text", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("model_alias", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('character', 'location', 'object', 'organization', 'other')",
            name="ck_entity_mention_type",
        ),
        sa.CheckConstraint(
            "start_offset >= 0 AND end_offset > start_offset",
            name="ck_entity_mention_offsets",
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_version_id"], ["manuscript_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "manuscript_version_id",
            "chapter_id",
            "start_offset",
            "end_offset",
            "entity_type",
        ),
    )
    op.create_index(
        "ix_entity_mentions_manuscript_version_id",
        "entity_mentions",
        ["manuscript_version_id"],
    )
    op.create_index("ix_entity_mentions_chapter_id", "entity_mentions", ["chapter_id"])
    op.create_index("ix_entity_mentions_scene_id", "entity_mentions", ["scene_id"])
    op.create_index("ix_entity_mentions_chunk_id", "entity_mentions", ["chunk_id"])


def downgrade() -> None:
    op.drop_table("entity_mentions")
