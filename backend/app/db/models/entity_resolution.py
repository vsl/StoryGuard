import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (
        CheckConstraint("entity_type IN ('character','facility','gpe','location','organization','vehicle')", name="ck_entity_type"),
        CheckConstraint("status IN ('active','merged','needs_review')", name="ck_entity_status"),
        CheckConstraint("merged_into_id IS NULL OR merged_into_id <> id", name="ck_entity_not_self"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    manuscript_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscript_versions.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(16))
    canonical_name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="needs_review", server_default="needs_review")
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id", ondelete="SET NULL"), index=True)


class EntityAlias(Base):
    __tablename__ = "entity_aliases"
    __table_args__ = (UniqueConstraint("entity_id", "alias"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    alias: Mapped[str] = mapped_column(Text)
    normalized_alias: Mapped[str] = mapped_column(Text)


class ResolutionCandidate(Base):
    __tablename__ = "entity_resolution_candidates"
    __table_args__ = (
        UniqueConstraint("manuscript_version_id", "left_mention_id", "right_mention_id"),
        CheckConstraint("left_mention_id < right_mention_id", name="ck_resolution_pair_order"),
        CheckConstraint("llm_decision IN ('merge','keep_separate','needs_review')", name="ck_resolution_llm_decision"),
        CheckConstraint("applied_decision IN ('merge','keep_separate')", name="ck_resolution_applied_decision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    manuscript_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscript_versions.id", ondelete="CASCADE"), index=True)
    left_mention_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entity_mentions.id", ondelete="CASCADE"), index=True)
    right_mention_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entity_mentions.id", ondelete="CASCADE"), index=True)
    llm_decision: Mapped[str | None] = mapped_column(String(16))
    applied_decision: Mapped[str | None] = mapped_column(String(16))
    error_code: Mapped[str | None] = mapped_column(String(64))
    evidence_ids: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    model_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResolutionDecision(Base):
    """Append-only application audit. Original entity/mention links are never rewritten."""

    __tablename__ = "entity_resolution_decisions"
    __table_args__ = (
        UniqueConstraint("candidate_id", "source", "attempt", name="uq_resolution_decision_attempt"),
        CheckConstraint("attempt >= 1 AND (source = 'model' OR attempt = 1)", name="ck_resolution_decision_attempt"),
        CheckConstraint("source IN ('model','human','automatic')", name="ck_resolution_source"),
        CheckConstraint("decision IN ('merge','keep_separate','needs_review')", name="ck_resolution_decision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    manuscript_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscript_versions.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entity_resolution_candidates.id", ondelete="SET NULL"), index=True)
    decision: Mapped[str | None] = mapped_column(String(16))
    attempt: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    source: Mapped[str] = mapped_column(String(16))
    evidence: Mapped[list] = mapped_column(JSONB)
    before: Mapped[dict] = mapped_column(JSONB)
    after: Mapped[dict] = mapped_column(JSONB)
    model_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
