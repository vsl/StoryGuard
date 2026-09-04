import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ManuscriptVersion(Base):
    __tablename__ = "manuscript_versions"
    __table_args__ = (
        CheckConstraint("version_number > 0", name="ck_manuscript_version_number"),
        CheckConstraint("file_size > 0", name="ck_manuscript_file_size"),
        CheckConstraint(
            "status IN ('uploaded', 'processing', 'ready', 'failed', 'archived', 'cancelled')",
            name="ck_manuscript_status",
        ),
        UniqueConstraint("project_id", "version_number"),
        UniqueConstraint("object_key"),
        CheckConstraint(
            "extraction_model IN ('gemma4-e4b', 'gliner2.5-base-v1', 'qwen3.5-9b')",
            name="ck_manuscript_extraction_model",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(16), default="uploaded", server_default="uploaded"
    )
    object_key: Mapped[str] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(128))
    file_size: Mapped[int] = mapped_column(BigInteger)
    content_hash: Mapped[str] = mapped_column(String(64))
    pipeline_version: Mapped[str] = mapped_column(
        String(32), default="v1", server_default="v1"
    )
    parse_metadata: Mapped[dict | None] = mapped_column(JSON)
    extraction_model: Mapped[str] = mapped_column(
        String(64), default="gemma4-e4b", server_default="gemma4-e4b"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
