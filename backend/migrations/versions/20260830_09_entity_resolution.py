"""Add version-scoped identity anchors, candidate pairs and reversible decisions."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "20260830_09"
down_revision = "20260830_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("manuscript_version_id", sa.Uuid(), sa.ForeignKey("manuscript_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), server_default="needs_review", nullable=False),
        sa.Column("merged_into_id", sa.Uuid(), sa.ForeignKey("entities.id", ondelete="SET NULL")),
        sa.CheckConstraint("entity_type IN ('character','location','object','organization','other')", name="ck_entity_type"),
        sa.CheckConstraint("status IN ('active','merged','needs_review')", name="ck_entity_status"),
        sa.CheckConstraint("merged_into_id IS NULL OR merged_into_id <> id", name="ck_entity_not_self"),
    )
    op.create_table(
        "entity_aliases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entity_id", sa.Uuid(), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("normalized_alias", sa.Text(), nullable=False),
        sa.UniqueConstraint("entity_id", "alias"),
    )
    op.add_column("entity_mentions", sa.Column("entity_id", sa.Uuid()))
    op.create_foreign_key("fk_entity_mentions_entity_id", "entity_mentions", "entities", ["entity_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_entity_mentions_entity_id", "entity_mentions", ["entity_id"])
    op.create_table(
        "entity_resolution_candidates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("manuscript_version_id", sa.Uuid(), sa.ForeignKey("manuscript_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("left_mention_id", sa.Uuid(), sa.ForeignKey("entity_mentions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("right_mention_id", sa.Uuid(), sa.ForeignKey("entity_mentions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("llm_decision", sa.String(16)),
        sa.Column("applied_decision", sa.String(16)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("evidence_ids", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("model_metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("manuscript_version_id", "left_mention_id", "right_mention_id"),
        sa.CheckConstraint("left_mention_id < right_mention_id", name="ck_resolution_pair_order"),
        sa.CheckConstraint("llm_decision IN ('merge','keep_separate','needs_review')", name="ck_resolution_llm_decision"),
        sa.CheckConstraint("applied_decision IN ('merge','keep_separate')", name="ck_resolution_applied_decision"),
    )
    op.create_table(
        "entity_resolution_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("manuscript_version_id", sa.Uuid(), sa.ForeignKey("manuscript_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("entity_resolution_candidates.id", ondelete="SET NULL")),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("before", postgresql.JSONB(), nullable=False),
        sa.Column("after", postgresql.JSONB(), nullable=False),
        sa.Column("model_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("candidate_id", "source"),
        sa.CheckConstraint("source IN ('model','human','automatic')", name="ck_resolution_source"),
        sa.CheckConstraint("decision IN ('merge','keep_separate','needs_review')", name="ck_resolution_decision"),
    )
    for table, columns in {
        "entities": ("manuscript_version_id", "merged_into_id"),
        "entity_aliases": ("entity_id",),
        "entity_resolution_candidates": ("manuscript_version_id", "left_mention_id", "right_mention_id"),
        "entity_resolution_decisions": ("manuscript_version_id", "candidate_id"),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    op.drop_table("entity_resolution_decisions")
    op.drop_table("entity_resolution_candidates")
    op.drop_index("ix_entity_mentions_entity_id", table_name="entity_mentions")
    op.drop_constraint("fk_entity_mentions_entity_id", "entity_mentions", type_="foreignkey")
    op.drop_column("entity_mentions", "entity_id")
    op.drop_table("entity_aliases")
    op.drop_table("entities")
