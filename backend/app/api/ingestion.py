import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.projects import _project_or_404
from app.ai.extraction_models import ExtractionModel, extraction_model_catalog
from app.db.models.job_run import JobRun
from app.db.models.manuscript_version import ManuscriptVersion
from app.db.models.narrative import Chapter
from app.db.session import get_session
from app.manuscripts import create_manuscript_version
from app.queue.tasks.ingestion import parse_and_ingest_manuscript
from app.schemas.ingestion import (
    ChapterDetailRead,
    ChapterRead,
    JobRead,
    ExtractionModelCatalog,
    ManuscriptUploadRead,
    ManuscriptVersionRead,
)

router = APIRouter(tags=["ingestion"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/api/extraction-models", response_model=ExtractionModelCatalog)
async def list_extraction_models() -> dict:
    return extraction_model_catalog()


async def _version_or_404(
    project_id: uuid.UUID, version_id: uuid.UUID, session: AsyncSession
) -> ManuscriptVersion:
    version = await session.scalar(
        select(ManuscriptVersion).where(
            ManuscriptVersion.id == version_id,
            ManuscriptVersion.project_id == project_id,
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Manuscript version not found")
    return version


@router.post(
    "/api/projects/{project_id}/manuscripts",
    response_model=ManuscriptUploadRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_manuscript(
    project_id: uuid.UUID,
    file: Annotated[UploadFile, File()],
    session: Session,
    extraction_model: Annotated[ExtractionModel | None, Form()] = None,
) -> ManuscriptUploadRead | JSONResponse:
    if not file.filename or not file.content_type:
        raise HTTPException(status_code=400, detail="The manuscript file is invalid")
    try:
        version = await create_manuscript_version(
            session, project_id, file.filename, file.content_type, file.file,
            extraction_model=extraction_model,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = JobRun(
        job_type="parse_and_ingest_manuscript",
        project_id=project_id,
        manuscript_version_id=version.id,
        stage="file_uploaded",
        idempotency_key=f"parse:{version.id}",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    try:
        await parse_and_ingest_manuscript.kiq(str(job.id))
    except Exception:
        job.status = "failed"
        job.error_code = "QUEUE_UNAVAILABLE"
        job.error_message_safe = "The manuscript could not be queued for processing."
        version.status = "failed"
        await session.commit()
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": job.error_code,
                    "message": job.error_message_safe,
                }
            },
        )
    return ManuscriptUploadRead(
        manuscript_version_id=version.id,
        version=f"v{version.version_number}",
        job_id=job.id,
        status=job.status,
        extraction_model=version.extraction_model,
    )


@router.get(
    "/api/projects/{project_id}/manuscripts",
    response_model=list[ManuscriptVersionRead],
)
async def list_manuscripts(
    project_id: uuid.UUID, session: Session
) -> list[ManuscriptVersion]:
    await _project_or_404(project_id, session)
    versions = await session.scalars(
        select(ManuscriptVersion)
        .where(ManuscriptVersion.project_id == project_id)
        .order_by(ManuscriptVersion.version_number.desc())
    )
    return list(versions)


@router.get(
    "/api/projects/{project_id}/manuscripts/{version_id}",
    response_model=ManuscriptVersionRead,
)
async def get_manuscript(
    project_id: uuid.UUID, version_id: uuid.UUID, session: Session
) -> ManuscriptVersion:
    return await _version_or_404(project_id, version_id, session)


@router.get("/api/jobs/{job_id}", response_model=JobRead)
async def get_job(job_id: uuid.UUID, session: Session) -> JobRead:
    job = await session.get(JobRun, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    now = datetime.now(timezone.utc)
    current_stage_elapsed_ms = (
        max(0, round((now - job.stage_started_at).total_seconds() * 1000))
        if job.status == "running" and job.stage_started_at is not None
        else None
    )
    return JobRead(
        id=job.id,
        status=job.status,
        stage=job.stage,
        completed=job.completed_units,
        total=job.total_units,
        error_code=job.error_code,
        error_message_safe=job.error_message_safe,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        stage_started_at=job.stage_started_at,
        stage_durations_ms=job.stage_durations_ms or {},
        current_stage_elapsed_ms=current_stage_elapsed_ms,
    )


async def _current_version_id(
    project_id: uuid.UUID, session: AsyncSession
) -> uuid.UUID | None:
    project = await _project_or_404(project_id, session)
    if project.current_manuscript_version_id is None:
        return None
    version = await session.scalar(
        select(ManuscriptVersion.id).where(
            ManuscriptVersion.id == project.current_manuscript_version_id,
            ManuscriptVersion.project_id == project_id,
            ManuscriptVersion.status == "ready",
        )
    )
    return version


@router.get(
    "/api/projects/{project_id}/chapters", response_model=list[ChapterRead]
)
async def list_chapters(
    project_id: uuid.UUID, session: Session
) -> list[ChapterRead]:
    version_id = await _current_version_id(project_id, session)
    if version_id is None:
        return []
    chapters = await session.scalars(
        select(Chapter)
        .where(Chapter.manuscript_version_id == version_id)
        .order_by(Chapter.ordinal)
    )
    return [
        ChapterRead(id=chapter.id, number=chapter.ordinal, title=chapter.title)
        for chapter in chapters
    ]


@router.get(
    "/api/projects/{project_id}/chapters/{chapter_id}",
    response_model=ChapterDetailRead,
)
async def get_chapter(
    project_id: uuid.UUID, chapter_id: uuid.UUID, session: Session
) -> ChapterDetailRead:
    version_id = await _current_version_id(project_id, session)
    chapter = (
        await session.scalar(
            select(Chapter).where(
                Chapter.id == chapter_id,
                Chapter.manuscript_version_id == version_id,
            )
        )
        if version_id is not None
        else None
    )
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return ChapterDetailRead(
        id=chapter.id,
        number=chapter.ordinal,
        title=chapter.title,
        text=chapter.text,
    )
