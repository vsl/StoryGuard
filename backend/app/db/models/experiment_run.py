import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExperimentRun(Base):
    __tablename__ = "experiment_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'scoring', 'completed', 'failed')",
            name="ck_experiment_run_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_experiment_run_attempts"),
        CheckConstraint(
            "(status IN ('queued', 'running', 'scoring') AND active_slot = 1) "
            "OR (status IN ('completed', 'failed') AND active_slot IS NULL)",
            name="ck_experiment_run_active_slot",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[str] = mapped_column(String(64))
    baseline_config_id: Mapped[str] = mapped_column(String(64))
    candidate_config_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(16), default="queued", server_default="queued"
    )
    stage: Mapped[str | None] = mapped_column(String(64))
    completed_units: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_units: Mapped[int] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    active_slot: Mapped[int | None] = mapped_column(Integer, unique=True)
    config_snapshot: Mapped[dict] = mapped_column(JSONB)
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    failures: Mapped[list | None] = mapped_column(JSONB)
    observability: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message_safe: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
