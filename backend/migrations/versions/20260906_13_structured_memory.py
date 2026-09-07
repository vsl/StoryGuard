"""Persist version-scoped facts, events, relationships, and evidence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260906_13"
down_revision = "20260831_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "structured_memory_chunk_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("job_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manuscript_version_id", sa.Uuid(), sa.ForeignKey("manuscript_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), sa.ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("raw_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("accepted_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejected_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("repair_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("model_alias", sa.String(128), nullable=False),
        sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("usage", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("rejection_reasons", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("job_id", "chunk_id"),
        sa.CheckConstraint("status IN ('completed','failed')", name="ck_memory_chunk_status"),
        sa.CheckConstraint(
            "raw_count >= 0 AND accepted_count >= 0 AND rejected_count >= 0 AND repair_count >= 0",
            name="ck_memory_chunk_counts",
        ),
    )
    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("manuscript_version_id", sa.Uuid(), sa.ForeignKey("manuscript_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", sa.Uuid(), sa.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_id", sa.Uuid(), sa.ForeignKey("scenes.id", ondelete="SET NULL")),
        sa.Column("chunk_id", sa.Uuid(), sa.ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.UniqueConstraint("manuscript_version_id", "chunk_id", "start_offset", "end_offset"),
        sa.CheckConstraint("start_offset >= 0 AND end_offset > start_offset", name="ck_evidence_offsets"),
    )
    op.create_table(
        "facts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("job_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manuscript_version_id", sa.Uuid(), sa.ForeignKey("manuscript_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_entity_id", sa.Uuid(), sa.ForeignKey("entities.id", ondelete="SET NULL")),
        sa.Column("subject_text", sa.Text(), nullable=False),
        sa.Column("predicate", sa.String(64), nullable=False),
        sa.Column("object_entity_id", sa.Uuid(), sa.ForeignKey("entities.id", ondelete="SET NULL")),
        sa.Column("object_text", sa.Text(), nullable=False),
        sa.Column("fact_type", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("model_alias", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "fact_type IN ('attribute','state','possession','location','role','affiliation','world_rule')",
            name="ck_fact_type",
        ),
        sa.CheckConstraint("status IN ('active','superseded')", name="ck_fact_status"),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("job_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manuscript_version_id", sa.Uuid(), sa.ForeignKey("manuscript_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("chronological_time_raw", sa.Text()),
        sa.Column("chronological_time_normalized", sa.String(128)),
        sa.Column("narrative_chapter_ordinal", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("model_alias", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "relationships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("job_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manuscript_version_id", sa.Uuid(), sa.ForeignKey("manuscript_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_entity_id", sa.Uuid(), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.String(32), nullable=False),
        sa.Column("target_entity_id", sa.Uuid(), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("start_event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="SET NULL")),
        sa.Column("end_event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("model_alias", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('active','ended')", name="ck_relationship_status"),
    )
    op.create_table(
        "fact_evidence",
        sa.Column("fact_id", sa.Uuid(), sa.ForeignKey("facts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("evidence_id", sa.Uuid(), sa.ForeignKey("evidence.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "event_evidence",
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("evidence_id", sa.Uuid(), sa.ForeignKey("evidence.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "relationship_evidence",
        sa.Column("relationship_id", sa.Uuid(), sa.ForeignKey("relationships.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("evidence_id", sa.Uuid(), sa.ForeignKey("evidence.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "event_participants",
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("entity_id", sa.Uuid(), sa.ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "event_locations",
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("entity_id", sa.Uuid(), sa.ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True),
    )
    for table, columns in {
        "structured_memory_chunk_results": ("job_id", "manuscript_version_id", "chunk_id"),
        "evidence": ("manuscript_version_id", "chapter_id", "scene_id", "chunk_id"),
        "facts": ("job_id", "manuscript_version_id", "subject_entity_id", "object_entity_id"),
        "events": ("job_id", "manuscript_version_id"),
        "relationships": (
            "job_id", "manuscript_version_id", "source_entity_id", "target_entity_id",
            "start_event_id", "end_event_id",
        ),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table in (
        "event_locations",
        "event_participants",
        "relationship_evidence",
        "event_evidence",
        "fact_evidence",
        "relationships",
        "events",
        "facts",
        "evidence",
        "structured_memory_chunk_results",
    ):
        op.drop_table(table)
