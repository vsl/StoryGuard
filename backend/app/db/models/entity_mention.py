import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EntityMention(Base):
    __tablename__ = "entity_mentions"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('character', 'location', 'object', 'organization', 'other')",
            name="ck_entity_mention_type",
        ),
        CheckConstraint(
            "start_offset >= 0 AND end_offset > start_offset",
            name="ck_entity_mention_offsets",
        ),
        UniqueConstraint(
            "manuscript_version_id",
            "chapter_id",
            "start_offset",
            "end_offset",
            "entity_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    manuscript_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manuscript_versions.id", ondelete="CASCADE"), index=True
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("scenes.id", ondelete="SET NULL"), index=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(16))
    surface_text: Mapped[str] = mapped_column(Text)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    prompt_version: Mapped[str] = mapped_column(String(64))
    model_alias: Mapped[str] = mapped_column(String(64))
