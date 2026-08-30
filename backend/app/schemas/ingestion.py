import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.ai.extraction_models import ExtractionModel


class ExtractionModelRead(BaseModel):
    id: ExtractionModel
    label: str
    description: str


class ExtractionModelCatalog(BaseModel):
    default: ExtractionModel
    items: list[ExtractionModelRead]


class ManuscriptVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_number: int
    status: str
    original_filename: str
    file_size: int
    pipeline_version: str
    created_at: datetime
    ready_at: datetime | None
    extraction_model: ExtractionModel


class ManuscriptUploadRead(BaseModel):
    manuscript_version_id: uuid.UUID
    version: str
    job_id: uuid.UUID
    status: str
    extraction_model: ExtractionModel


class JobRead(BaseModel):
    id: uuid.UUID
    status: str
    stage: str | None
    completed: int | None
    total: int | None
    error_code: str | None
    error_message_safe: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    stage_started_at: datetime | None
    stage_durations_ms: dict[str, int]
    current_stage_elapsed_ms: int | None


class ChapterRead(BaseModel):
    id: uuid.UUID
    number: int
    title: str | None


class ChapterDetailRead(ChapterRead):
    text: str
