import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (
        CheckConstraint("ordinal > 0", name="ck_chapter_ordinal"),
        UniqueConstraint("manuscript_version_id", "ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    manuscript_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manuscript_versions.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))


class Scene(Base):
    __tablename__ = "scenes"
    __table_args__ = (
        CheckConstraint("ordinal > 0", name="ck_scene_ordinal"),
        CheckConstraint(
            "start_offset >= 0 AND end_offset > start_offset",
            name="ck_scene_offsets",
        ),
        UniqueConstraint("chapter_id", "ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        CheckConstraint("ordinal > 0", name="ck_chunk_ordinal"),
        CheckConstraint(
            "start_offset >= 0 AND end_offset > start_offset",
            name="ck_chunk_offsets",
        ),
        UniqueConstraint("manuscript_version_id", "ordinal"),
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
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    embedding_version: Mapped[str | None] = mapped_column(String(32))
