import asyncio
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import EMBEDDING_VERSION, embed_documents
from app.db.models.job_run import JobRun
from app.db.models.manuscript_version import ManuscriptVersion
from app.db.models.narrative import Chapter, Chunk, Scene
from app.db.models.project import Project
from app.db.session import SessionLocal
from app.entity_mentions import extract_version_entities
from app.ai.retrieval import replace_version_chunks
from app.manuscripts import minio_client
from app.parsing import parse_manuscript
from app.queue.broker import broker


def _download(key: str) -> bytes:
    response = minio_client().get_object(os.environ["MINIO_BUCKET"], key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _finish_stage(job: JobRun, now: datetime) -> None:
    if job.stage and job.stage_started_at:
        durations = dict(job.stage_durations_ms or {})
        elapsed_ms = max(0, round((now - job.stage_started_at).total_seconds() * 1000))
        durations[job.stage] = durations.get(job.stage, 0) + elapsed_ms
        job.stage_durations_ms = durations
    job.stage_started_at = None


def _start_stage(job: JobRun, stage: str, now: datetime) -> None:
    _finish_stage(job, now)
    job.stage = stage
    job.stage_started_at = now


def cancel_ingestion(job: JobRun, version: ManuscriptVersion, reason: str) -> None:
    """Caller holds the project, job, and version locks, in that order."""
    now = _now()
    _finish_stage(job, now)
    job.status = version.status = "cancelled"
    job.completed_at = now
    job.error_code = reason
    job.error_message_safe = (
        "Processing was replaced by a newer upload."
        if reason == "SUPERSEDED"
        else "Processing was cancelled."
    )


async def latest_accepted_version(session: AsyncSession, project_id: uuid.UUID) -> int:
    return await session.scalar(
        select(func.coalesce(func.max(ManuscriptVersion.version_number), 0))
        .join(JobRun, JobRun.manuscript_version_id == ManuscriptVersion.id)
        .where(
            ManuscriptVersion.project_id == project_id,
            JobRun.project_id == project_id,
            JobRun.job_type == "parse_and_ingest_manuscript",
            JobRun.stage.is_distinct_from("awaiting_dispatch"),
            JobRun.error_code.is_distinct_from("QUEUE_UNAVAILABLE"),
        )
    )


async def _mark_failed(
    job_id: uuid.UUID, error_code: str, error_message_safe: str
) -> bool:
    async with SessionLocal() as session, session.begin():
        job = await session.get(JobRun, job_id, with_for_update=True)
        if job is None or job.status in {"completed", "cancelled"}:
            return False
        now = _now()
        _finish_stage(job, now)
        job.status = "failed"
        job.error_code = error_code
        job.error_message_safe = error_message_safe
        job.completed_at = now
        if job.manuscript_version_id is not None:
            version = await session.get(
                ManuscriptVersion, job.manuscript_version_id, with_for_update=True
            )
            if version is not None:
                version.status = "failed"
        return True


async def run_parse_and_ingest(job_id: uuid.UUID) -> None:
    async with SessionLocal() as session, session.begin():
        job = await session.get(JobRun, job_id)
        if job is None:
            raise LookupError("Job not found")
        # Match upload/cancel/promotion lock order; dispatch commits before work starts.
        await session.get(Project, job.project_id, with_for_update=True)
        await session.refresh(job, with_for_update=True)
        if job.status in {"completed", "cancelled"} or job.stage == "awaiting_dispatch":
            return
        if job.manuscript_version_id is None:
            raise ValueError("Parsing job requires a manuscript version")
        version = await session.get(
            ManuscriptVersion, job.manuscript_version_id, with_for_update=True
        )
        if version is None:
            raise LookupError("Manuscript version not found")
        if version.project_id != job.project_id:
            raise ValueError("Job and manuscript version scopes do not match")
        if version.status == "cancelled":
            cancel_ingestion(job, version, "USER_CANCELLED")
            return
        if version.version_number < await latest_accepted_version(session, job.project_id):
            cancel_ingestion(job, version, "SUPERSEDED")
            return
        now = _now()
        job.status = "running"
        _start_stage(job, "parsing", now)
        job.attempts += 1
        job.started_at = job.started_at or now
        job.completed_at = None
        job.error_code = job.error_message_safe = None
        version.status = "processing"
        version_id, project_id = version.id, version.project_id
        filename, object_key = version.original_filename, version.object_key

    try:
        data = await asyncio.to_thread(_download, object_key)
        parsed = await asyncio.to_thread(parse_manuscript, filename, data)

        async with SessionLocal() as session, session.begin():
            job = await session.get(JobRun, job_id, with_for_update=True)
            if job is None or job.status == "cancelled":
                return
            version = await session.get(
                ManuscriptVersion, version_id, with_for_update=True
            )
            if (
                job.manuscript_version_id != version_id
                or version.project_id != job.project_id
            ):
                raise ValueError("Job scope changed during parsing")
            await session.execute(
                delete(Chapter).where(Chapter.manuscript_version_id == version.id)
            )

            chapters: list[Chapter] = []
            scenes: list[Scene] = []
            chunks: list[Chunk] = []
            chunk_ordinal = 0
            for parsed_chapter in parsed.chapters:
                chapter = Chapter(
                    id=uuid.uuid4(),
                    manuscript_version_id=version.id,
                    ordinal=parsed_chapter.ordinal,
                    title=parsed_chapter.title,
                    text=parsed_chapter.text,
                    content_hash=parsed_chapter.content_hash,
                )
                chapters.append(chapter)
                for parsed_scene in parsed_chapter.scenes:
                    scene = Scene(
                        id=uuid.uuid4(),
                        chapter_id=chapter.id,
                        ordinal=parsed_scene.ordinal,
                        text=parsed_scene.text,
                        start_offset=parsed_scene.start_offset,
                        end_offset=parsed_scene.end_offset,
                        content_hash=parsed_scene.content_hash,
                    )
                    scenes.append(scene)
                    for parsed_chunk in parsed_scene.chunks:
                        chunk_ordinal += 1
                        chunks.append(
                            Chunk(
                                manuscript_version_id=version.id,
                                chapter_id=chapter.id,
                                scene_id=scene.id,
                                ordinal=chunk_ordinal,
                                text=parsed_chunk.text,
                                start_offset=parsed_chunk.start_offset,
                                end_offset=parsed_chunk.end_offset,
                                content_hash=parsed_chunk.content_hash,
                            )
                        )
            session.add_all(chapters)
            await session.flush()
            session.add_all(scenes)
            await session.flush()
            session.add_all(chunks)
            await session.flush()

            version.parse_metadata = parsed.metadata
            _start_stage(job, "embedding", _now())
    except Exception:
        if await _mark_failed(
            job_id,
            "MANUSCRIPT_PARSING_FAILED",
            "The manuscript could not be parsed.",
        ):
            raise
        return

    try:
        chapter_ordinals = {chapter.id: chapter.ordinal for chapter in chapters}
        documents = [
            {
                "chunk_id": str(chunk.id),
                "project_id": str(project_id),
                "manuscript_version_id": str(version_id),
                "chapter_id": str(chunk.chapter_id),
                "chapter_ordinal": chapter_ordinals[chunk.chapter_id],
                "scene_id": str(chunk.scene_id) if chunk.scene_id else None,
                "text": chunk.text,
                "content_hash": chunk.content_hash,
            }
            for chunk in chunks
        ]
        vectors = await asyncio.to_thread(
            embed_documents, [str(document["text"]) for document in documents]
        )
        if len(vectors) != len(documents):
            raise ValueError("Embedding count does not match chunk count")
        for document, vector in zip(documents, vectors, strict=True):
            document["embedding_version"] = EMBEDDING_VERSION
            document["embedding"] = vector
    except Exception:
        if await _mark_failed(
            job_id,
            "EMBEDDING_FAILED",
            "The manuscript embeddings could not be created.",
        ):
            raise
        return

    try:
        async with SessionLocal() as session, session.begin():
            job = await session.get(JobRun, job_id, with_for_update=True)
            if job is not None and job.status == "cancelled":
                return
            if job is None or job.manuscript_version_id != version_id:
                raise ValueError("Job scope changed during embedding")
            _start_stage(job, "indexing", _now())
        await replace_version_chunks(
            str(project_id),
            str(version_id),
            documents,
        )
        async with SessionLocal() as session, session.begin():
            job = await session.get(JobRun, job_id, with_for_update=True)
            if job is not None and job.status == "cancelled":
                return
            version = await session.get(ManuscriptVersion, version_id, with_for_update=True)
            if (
                job is None
                or version is None
                or job.manuscript_version_id != version.id
                or version.project_id != job.project_id
            ):
                raise ValueError("Job scope changed during indexing")
            await session.execute(
                update(Chunk)
                .where(Chunk.manuscript_version_id == version.id)
                .values(embedding_version=EMBEDDING_VERSION)
            )
            _start_stage(job, "entity_extraction", _now())
    except Exception:
        if await _mark_failed(
            job_id,
            "ELASTICSEARCH_INDEXING_FAILED",
            "The manuscript search index could not be created.",
        ):
            raise
        return

    try:
        await extract_version_entities(project_id, version_id)
        async with SessionLocal() as session, session.begin():
            project = await session.get(Project, project_id, with_for_update=True)
            job = await session.get(JobRun, job_id, with_for_update=True)
            if job is not None and job.status == "cancelled":
                return
            version = await session.get(ManuscriptVersion, version_id, with_for_update=True)
            if (
                job is None
                or version is None
                or project is None
                or job.manuscript_version_id != version.id
                or version.project_id != job.project_id
            ):
                raise ValueError("Job scope changed during entity extraction")
            if version.version_number < await latest_accepted_version(session, project_id):
                cancel_ingestion(job, version, "SUPERSEDED")
                return
            current = (
                await session.get(ManuscriptVersion, project.current_manuscript_version_id)
                if project.current_manuscript_version_id else None
            )
            now = _now()
            _finish_stage(job, now)
            job.status = "completed"
            job.stage = "entities_extracted"
            job.completed_units = job.total_units = len(chapters)
            job.completed_at = now
            version.status = "ready"
            version.ready_at = job.completed_at
            if current is None or current.version_number < version.version_number:
                project.current_manuscript_version_id = version.id
    except Exception:
        if await _mark_failed(
            job_id,
            "ENTITY_EXTRACTION_FAILED",
            "The manuscript entities could not be extracted.",
        ):
            raise


@broker.task(retry_on_error=True)
async def parse_and_ingest_manuscript(job_id: str) -> None:
    await run_parse_and_ingest(uuid.UUID(job_id))
