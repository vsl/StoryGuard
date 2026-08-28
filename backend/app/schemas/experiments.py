import uuid
from datetime import datetime

from pydantic import BaseModel


class ExperimentDatasetRead(BaseModel):
    id: str
    name: str
    purpose: str
    stories: list[str]
    query_count: int
    revision: str
    manifest_sha256: str
    promotion_eligible: bool = False


class ExperimentConfigRead(BaseModel):
    id: str
    name: str
    retrieval_strategy: str
    reranker: bool


class ExperimentCreate(BaseModel):
    dataset_id: str
    baseline_config_id: str
    candidate_config_id: str


class MetricComparison(BaseModel):
    baseline: float
    candidate: float


class ExperimentRead(BaseModel):
    id: uuid.UUID
    status: str
    stage: str | None
    dataset: str
    baseline: str
    candidate: str
    completed: int
    total: int
    diagnostic_only: bool = True
    metrics: dict[str, MetricComparison] | None
    error_code: str | None
    error_message_safe: str | None
    observability: dict | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ExperimentFailureRead(BaseModel):
    id: str
    type: str
    question: str
    summary: str
    baseline_output: str
    candidate_output: str
    trace_id: str | None = None
