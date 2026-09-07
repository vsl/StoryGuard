import uuid

from pydantic import BaseModel, ConfigDict

from app.schemas.ingestion import JobRead


class MemoryStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manuscript_version_id: uuid.UUID
    rebuild: bool = False


class MemoryRunRead(BaseModel):
    job_id: uuid.UUID
    manuscript_version_id: uuid.UUID
    status: str


class MemoryStatusRead(BaseModel):
    manuscript_version_id: uuid.UUID | None
    job: JobRead | None
    completed_chunks: int = 0
    failed_chunks: int = 0
    total_chunks: int = 0
    facts: int = 0
    events: int = 0
    relationships: int = 0


class MemoryEvidenceRead(BaseModel):
    id: uuid.UUID
    manuscript_version_id: uuid.UUID
    chapter_id: uuid.UUID
    scene_id: uuid.UUID | None
    chunk_id: uuid.UUID
    chapter: str
    text: str
    start_offset: int
    end_offset: int


class FactRead(BaseModel):
    id: uuid.UUID
    subject: str
    predicate: str
    value: str
    fact_type: str
    confidence: float | None
    source: str | None
    status: str
    evidence: list[MemoryEvidenceRead]


class EventRead(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    description: str
    chronological_time: str | None
    chronological_time_normalized: str | None
    narrative_position: str
    chapter: str
    location: str | None
    participants: list[str]
    evidence: list[MemoryEvidenceRead]


class RelationshipRead(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    source: str
    target: str
    status: str
    start_event_id: uuid.UUID | None
    end_event_id: uuid.UUID | None
    evidence: list[MemoryEvidenceRead]
