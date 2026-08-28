import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.retrieval import retrieve_hybrid, retrieve_hybrid_reranked
from app.db.models.project import Project
from app.db.models.manuscript_version import ManuscriptVersion
from app.db.models.narrative import Chapter
from app.db.session import get_session
from app.schemas.projects import (
    ProjectCreate,
    ProjectRead,
    ProjectSearchRead,
    ProjectUpdate,
    SearchMatchRead,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])
Session = Annotated[AsyncSession, Depends(get_session)]
LOGGER = logging.getLogger(__name__)


async def _project_or_404(project_id: uuid.UUID, session: AsyncSession) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _project_read(project: Project, session: AsyncSession) -> ProjectRead:
    version = (
        await session.scalar(
            select(ManuscriptVersion).where(
                ManuscriptVersion.id == project.current_manuscript_version_id,
                ManuscriptVersion.project_id == project.id,
                ManuscriptVersion.status == "ready",
            )
        )
        if project.current_manuscript_version_id is not None
        else None
    )
    chapter_count = (
        await session.scalar(
            select(func.count()).select_from(Chapter).where(
                Chapter.manuscript_version_id == version.id
            )
        )
        if version is not None
        else None
    )
    return ProjectRead.model_validate(project).model_copy(
        update={
            "current_manuscript_version": (
                f"v{version.version_number}" if version is not None else None
            ),
            "chapter_count": chapter_count,
        }
    )


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, session: Session) -> ProjectRead:
    project = Project(**payload.model_dump())
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return await _project_read(project, session)


@router.get("", response_model=list[ProjectRead])
async def list_projects(session: Session) -> list[ProjectRead]:
    result = await session.scalars(
        select(Project).order_by(Project.created_at.desc(), Project.id.desc())
    )
    return [await _project_read(project, session) for project in result]


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: uuid.UUID, session: Session) -> ProjectRead:
    return await _project_read(await _project_or_404(project_id, session), session)


@router.get("/{project_id}/search", response_model=ProjectSearchRead)
async def search_project(
    project_id: uuid.UUID,
    session: Session,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    rerank: bool = True,
) -> ProjectSearchRead | JSONResponse:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=422, detail="Search query must not be empty")
    project = await _project_or_404(project_id, session)
    version_id = project.current_manuscript_version_id
    if version_id is None:
        return ProjectSearchRead(manuscript_matches=[])
    ready_version_id = await session.scalar(
        select(ManuscriptVersion.id).where(
            ManuscriptVersion.id == version_id,
            ManuscriptVersion.project_id == project_id,
            ManuscriptVersion.status == "ready",
        )
    )
    if ready_version_id is None:
        return ProjectSearchRead(manuscript_matches=[])

    retrieve = retrieve_hybrid_reranked if rerank else retrieve_hybrid
    try:
        matches = await retrieve(query, str(project_id), str(ready_version_id), 10)
    except Exception:
        LOGGER.exception(
            "Project search failed",
            extra={
                "project_id": str(project_id),
                "manuscript_version_id": str(version_id),
            },
        )
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "RETRIEVAL_UNAVAILABLE",
                    "message": "Manuscript search is temporarily unavailable.",
                }
            },
        )
    return ProjectSearchRead(
        manuscript_matches=[
            SearchMatchRead(
                chunk_id=match.chunk_id,
                chapter_id=match.chapter_id,
                chapter_ordinal=match.chapter_ordinal,
                scene_id=match.scene_id,
                text=match.text,
                score=match.score,
            )
            for match in matches
        ]
    )


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: uuid.UUID, payload: ProjectUpdate, session: Session
) -> ProjectRead:
    project = await _project_or_404(project_id, session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await session.commit()
    await session.refresh(project)
    return await _project_read(project, session)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: uuid.UUID, session: Session) -> Response:
    project = await _project_or_404(project_id, session)
    await session.delete(project)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
