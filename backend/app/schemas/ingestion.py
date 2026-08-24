import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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


class ManuscriptUploadRead(BaseModel):
    manuscript_version_id: uuid.UUID
    version: str
    job_id: uuid.UUID
    status: str


class JobRead(BaseModel):
    id: uuid.UUID
    status: str
    stage: str | None
    completed: int | None
    total: int | None
    error_code: str | None
    error_message_safe: str | None


class ChapterRead(BaseModel):
    id: uuid.UUID
    number: int
    title: str | None


class ChapterDetailRead(ChapterRead):
    text: str
