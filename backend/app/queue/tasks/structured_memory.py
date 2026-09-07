import logging
import os
import time
import uuid
from datetime import datetime, timezone

import httpx
from langsmith import traceable
from sqlalchemy import func, select, update

from app.ai.entity_extraction import MODEL_ALIAS
from app.ai.structured_memory import PROMPT_VERSION, StructuredMemoryError, extract_structured_memory
from app.ai.tracing import annotate_trace
from app.db.models.job_run import JobRun
from app.db.models.structured_memory import Fact, MemoryChunkResult
from app.db.session import SessionLocal
from app.entity_resolution import ResolutionConflict, current_scope
from app.queue.broker import broker
from app.queue.tasks.ingestion import _finish_stage, _start_stage
from app.structured_memory import (
    MemoryConflict,
    MemoryIndex,
    chunk_inputs,
    persist_chunk,
    resolution_state_hash,
)

logger = logging.getLogger(__name__)


def _model_error(exc: Exception) -> str | None:
    if isinstance(exc, StructuredMemoryError):
        return "INVALID_MODEL_OUTPUT"
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return "MODEL_TIMEOUT"
    if isinstance(exc, (ConnectionError, httpx.TransportError)):
        return "MODEL_CONNECTION_ERROR"
    if isinstance(exc, httpx.HTTPStatusError):
        return "MODEL_RATE_LIMITED" if exc.response.status_code == 429 else "MODEL_REQUEST_FAILED"
    return None


async def _mark_failed(job_id: uuid.UUID, code: str, message: str) -> None:
    async with SessionLocal() as session, session.begin():
        job = await session.get(JobRun, job_id, with_for_update=True)
        if job is None or job.status in {"completed", "cancelled"}:
            return
        now = datetime.now(timezone.utc)
        _finish_stage(job, now)
        job.status = "failed"
        job.error_code = code
        job.error_message_safe = message
        job.completed_at = now


@traceable(
    name="structured_memory_job",
    run_type="chain",
    process_inputs=lambda inputs: {"job_id": str(inputs["job_id"])},
    process_outputs=lambda _: {},
)
async def run_structured_memory_job(job_id: uuid.UUID) -> None:
    attempt = None
    try:
        async with SessionLocal() as session, session.begin():
            job = await session.get(JobRun, job_id, with_for_update=True)
            if job is None or job.job_type != "structured_memory" or job.status != "queued":
                return
            version = await current_scope(
                session, job.project_id, job.manuscript_version_id, lock=True
            )
            resolution_done = await session.scalar(select(JobRun.id).where(
                JobRun.job_type == "entity_resolution",
                JobRun.project_id == job.project_id,
                JobRun.manuscript_version_id == version.id,
                JobRun.status == "completed",
            ).limit(1))
            if resolution_done is None:
                raise MemoryConflict("Entity resolution must complete first")
            expected_state = job.idempotency_key.split(":retry:", 1)[0].rsplit(":", 1)[1]
            if await resolution_state_hash(session, version.id) != expected_state:
                raise MemoryConflict("Entity resolution changed before extraction")
            sources = await chunk_inputs(session, version.id)
            now = datetime.now(timezone.utc)
            job.status = "running"
            job.attempts += 1
            attempt = job.attempts
            job.started_at = job.started_at or now
            job.completed_at = None
            job.completed_units = 0
            job.total_units = len(sources)
            job.error_code = job.error_message_safe = None
            _start_stage(job, "extracting_story_memory", now)
            project_id, version_id = job.project_id, version.id
            annotate_trace(metadata={
                "job_id": str(job_id),
                "project_id": str(project_id),
                "manuscript_version_id": str(version_id),
                "prompt_version": PROMPT_VERSION,
                "chunk_count": len(sources),
            })

        index = MemoryIndex()
        async with httpx.AsyncClient(
            base_url=os.environ["LITELLM_URL"],
            headers={"Authorization": f"Bearer {os.environ['LITELLM_API_KEY']}"},
            timeout=httpx.Timeout(180, connect=10),
        ) as client:
            for source in sources:
                started = time.monotonic()
                result = None
                error_code = None
                try:
                    result = await extract_structured_memory(
                        source.extraction, PROMPT_VERSION, client
                    )
                except Exception as exc:
                    error_code = _model_error(exc)
                    if error_code is None:
                        raise

                async with SessionLocal() as session, session.begin():
                    await current_scope(session, project_id, version_id, lock=True)
                    if await resolution_state_hash(session, version_id) != expected_state:
                        raise MemoryConflict("Entity resolution changed during extraction")
                    job = await session.get(JobRun, job_id, with_for_update=True)
                    if (
                        job is None or job.status != "running"
                        or job.attempts != attempt
                    ):
                        return
                    if result is not None:
                        await persist_chunk(
                            session, job_id, version_id, source, result, index
                        )
                    session.add(MemoryChunkResult(
                        job_id=job_id,
                        manuscript_version_id=version_id,
                        chunk_id=source.chunk.id,
                        status="failed" if error_code else "completed",
                        error_code=error_code,
                        raw_count=result.raw_count if result else 0,
                        accepted_count=result.memory.accepted_count if result else 0,
                        rejected_count=result.memory.rejected_count if result else 0,
                        repair_count=result.repair_count if result else 0,
                        prompt_version=PROMPT_VERSION,
                        model_alias=result.model if result else MODEL_ALIAS,
                        latency_ms=round((time.monotonic() - started) * 1000),
                        usage=result.usage if result else {},
                        rejection_reasons=(
                            list(result.memory.rejection_reasons) if result else []
                        ),
                    ))
                    job.completed_units = (job.completed_units or 0) + 1

        async with SessionLocal() as session, session.begin():
            await current_scope(session, project_id, version_id, lock=True)
            if await resolution_state_hash(session, version_id) != expected_state:
                raise MemoryConflict("Entity resolution changed before completion")
            job = await session.get(JobRun, job_id, with_for_update=True)
            if job is None or job.status != "running" or job.attempts != attempt:
                return
            failed = await session.scalar(select(func.count()).select_from(
                MemoryChunkResult
            ).where(
                MemoryChunkResult.job_id == job_id,
                MemoryChunkResult.status == "failed",
            ))
            now = datetime.now(timezone.utc)
            _finish_stage(job, now)
            job.completed_at = now
            if failed == len(sources):
                job.status = "failed"
                job.stage = "failed"
                job.error_code = "STRUCTURED_MEMORY_ALL_CHUNKS_FAILED"
                job.error_message_safe = "Story memory could not be built; the previous result remains active."
                return
            coverage = (
                select(
                    MemoryChunkResult.job_id,
                    func.count().filter(
                        MemoryChunkResult.status == "completed"
                    ).label("completed_chunks"),
                )
                .group_by(MemoryChunkResult.job_id)
                .subquery()
            )
            key_prefix = (
                f"structured-memory:{version_id}:{PROMPT_VERSION}:{expected_state}"
            )
            best_prior = await session.scalar(
                select(func.max(coverage.c.completed_chunks))
                .select_from(coverage)
                .join(JobRun, JobRun.id == coverage.c.job_id)
                .where(
                    JobRun.id != job_id,
                    JobRun.job_type == "structured_memory",
                    JobRun.project_id == project_id,
                    JobRun.manuscript_version_id == version_id,
                    JobRun.status == "completed",
                    JobRun.idempotency_key.like(f"{key_prefix}%"),
                )
            )
            if best_prior is not None and len(sources) - failed < best_prior:
                job.status = "failed"
                job.stage = "failed"
                job.error_code = "STRUCTURED_MEMORY_NOT_IMPROVED"
                job.error_message_safe = (
                    "This attempt covered fewer manuscript chunks; "
                    "the previous result remains active."
                )
                return
            await session.execute(update(Fact).where(
                Fact.manuscript_version_id == version_id,
                Fact.job_id != job_id,
                Fact.status == "active",
            ).values(status="superseded"))
            job.status = "completed"
            job.stage = "completed_with_errors" if failed else "completed"
            job.error_code = "STRUCTURED_MEMORY_CHUNK_ERRORS" if failed else None
            job.error_message_safe = (
                f"{failed} manuscript chunks were omitted after model errors."
                if failed else None
            )
    except KeyError:
        await _mark_failed(
            job_id,
            "STRUCTURED_MEMORY_CONFIG_ERROR",
            "Story memory model configuration is unavailable.",
        )
        raise
    except (MemoryConflict, ResolutionConflict, LookupError) as exc:
        logger.warning(
            "Structured-memory scope guard failed job=%s reason=%s", job_id, str(exc)
        )
        await _mark_failed(
            job_id,
            "STRUCTURED_MEMORY_SCOPE_CHANGED",
            "Story memory could not be built for the current manuscript and resolved entities.",
        )
    except Exception:
        await _mark_failed(
            job_id,
            "STRUCTURED_MEMORY_FAILED",
            "Story memory could not be built; the previous result remains active.",
        )
        raise


@broker.task(retry_on_error=False)
async def build_structured_memory(job_id: str) -> None:
    await run_structured_memory_job(uuid.UUID(job_id))
