import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.ai.entity_resolution import Decision
from app.ai.entity_extraction import EntityType
from app.schemas.ingestion import JobRead


class ResolutionStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manuscript_version_id: uuid.UUID


class ResolutionAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["merge", "keep_separate"]


class ResolutionRunRead(BaseModel):
    job_id: uuid.UUID
    manuscript_version_id: uuid.UUID
    status: str


class ResolutionEvidence(BaseModel):
    id: uuid.UUID
    manuscript_version_id: uuid.UUID
    chapter_id: uuid.UUID
    chapter: str
    text: str
    start_offset: int
    end_offset: int


class CandidateEntityRead(BaseModel):
    id: uuid.UUID
    name: str
    type: EntityType
    canonical_id: uuid.UUID


class ResolutionCandidateRead(BaseModel):
    id: uuid.UUID
    left: CandidateEntityRead
    right: CandidateEntityRead
    llm_decision: Decision | None
    applied_decision: Literal["merge", "keep_separate"] | None
    error_code: str | None
    latency_ms: float | None = None
    trace_id: str | None = None
    attempt: int = 0
    timeout_seconds: float | None = None
    http_status: int | None = None
    evidence: list[ResolutionEvidence]


class ResolutionCandidatesRead(BaseModel):
    manuscript_version_id: uuid.UUID | None
    items: list[ResolutionCandidateRead]
    total: int
    remaining: int
    review_count: int
    applied_count: int
    error_count: int
    successful_count: int
    coreference_merge_count: int = 0
    gemma_comparison_count: int = 0
    pipeline: Literal["gemma", "coreference_gemma"] = "gemma"
    request_timeout_seconds: float
    offset: int
    limit: int
    candidate_limit_reached: bool
    auto_apply: bool
    model: str
    job: JobRead | None


class EntityRead(BaseModel):
    id: uuid.UUID
    name: str
    type: EntityType
    status: str
    aliases: list[str]
    evidence: list[ResolutionEvidence] = []
