import asyncio
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.db.models.job_run import JobRun
from app.db.models.manuscript_version import ManuscriptVersion
from app.db.models.narrative import Chapter, Chunk, Scene
from app.db.session import SessionLocal
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


async def _mark_failed(job_id: uuid.UUID) -> None:
    async with SessionLocal() as session, session.begin():
        job = await session.get(JobRun, job_id, with_for_update=True)
        if job is None or job.status == "completed":
            return
        job.status = "failed"
        job.error_code = "MANUSCRIPT_PARSING_FAILED"
        job.error_message_safe = "The manuscript could not be parsed."
        job.completed_at = datetime.now(timezone.utc)
        if job.manuscript_version_id is not None:
            version = await session.get(
                ManuscriptVersion, job.manuscript_version_id, with_for_update=True
            )
            if version is not None:
                version.status = "failed"


async def run_parse_and_ingest(job_id: uuid.UUID) -> None:
    async with SessionLocal() as session, session.begin():
        job = await session.scalar(
            select(JobRun).where(JobRun.id == job_id).with_for_update()
        )
        if job is None:
            raise LookupError("Job not found")
        if job.status == "completed":
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
        job.status = "running"
        job.stage = "parsing"
        job.attempts += 1
        job.started_at = job.started_at or datetime.now(timezone.utc)
        job.completed_at = None
        job.error_code = job.error_message_safe = None
        version.status = "processing"
        version_id = version.id
        filename, object_key = version.original_filename, version.object_key

    try:
        data = await asyncio.to_thread(_download, object_key)
        parsed = await asyncio.to_thread(parse_manuscript, filename, data)

        async with SessionLocal() as session, session.begin():
            job = await session.get(JobRun, job_id, with_for_update=True)
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

            version.parse_metadata = parsed.metadata
            job.status = "completed"
            job.stage = "parsed"
            job.completed_units = job.total_units = len(parsed.chapters)
            job.completed_at = datetime.now(timezone.utc)
    except Exception:
        await _mark_failed(job_id)
        raise


@broker.task(retry_on_error=True)
async def parse_and_ingest_manuscript(job_id: str) -> None:
    await run_parse_and_ingest(uuid.UUID(job_id))
