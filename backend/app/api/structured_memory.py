import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.structured_memory import PROMPT_VERSION
from app.api.ingestion import _current_version_id, get_job
from app.db.models.entity_resolution import Entity
from app.db.models.job_run import JobRun
from app.db.models.narrative import Chapter
from app.db.models.structured_memory import (
    Event,
    EventEvidence,
    EventLocation,
    EventParticipant,
    Evidence,
    Fact,
    FactEvidence,
    MemoryChunkResult,
    Relationship,
    RelationshipEvidence,
)
from app.db.session import get_session
from app.entity_resolution import ResolutionConflict, canonical_id, current_scope, entity_map
from app.queue.tasks.structured_memory import build_structured_memory
from app.schemas.structured_memory import (
    EventRead,
    FactRead,
    MemoryEvidenceRead,
    MemoryRunRead,
    MemoryStart,
    MemoryStatusRead,
    RelationshipRead,
)
from app.structured_memory import resolution_state_hash


router = APIRouter(prefix="/api/projects/{project_id}", tags=["structured-memory"])
Session = Annotated[AsyncSession, Depends(get_session)]


async def _latest_job(
    session: AsyncSession, project_id: uuid.UUID, version_id: uuid.UUID,
    *, completed: bool = False,
) -> JobRun | None:
    state_hash = await resolution_state_hash(session, version_id)
    key_prefix = f"structured-memory:{version_id}:{PROMPT_VERSION}:{state_hash}"
    query = select(JobRun).where(
        JobRun.project_id == project_id,
        JobRun.manuscript_version_id == version_id,
        JobRun.job_type == "structured_memory",
        JobRun.idempotency_key.like(f"{key_prefix}%"),
    )
    if completed:
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
        query = query.where(JobRun.status == "completed")
        query = query.outerjoin(coverage, coverage.c.job_id == JobRun.id).order_by(
            func.coalesce(coverage.c.completed_chunks, 0).desc(),
            JobRun.created_at.desc(),
            JobRun.id.desc(),
        )
    else:
        query = query.order_by(JobRun.created_at.desc(), JobRun.id.desc())
    return await session.scalar(query.limit(1))


async def _evidence_map(session, association, owner_column, owner_ids) -> dict:
    grouped = defaultdict(list)
    if not owner_ids:
        return grouped
    rows = (await session.execute(
        select(owner_column, Evidence, Chapter)
        .join(Evidence, association.evidence_id == Evidence.id)
        .join(Chapter, Evidence.chapter_id == Chapter.id)
        .where(owner_column.in_(owner_ids))
        .order_by(Chapter.ordinal, Evidence.start_offset)
    )).all()
    for owner_id, evidence, chapter in rows:
        grouped[owner_id].append(MemoryEvidenceRead(
            id=evidence.id,
            manuscript_version_id=evidence.manuscript_version_id,
            chapter_id=evidence.chapter_id,
            scene_id=evidence.scene_id,
            chunk_id=evidence.chunk_id,
            chapter=chapter.title or f"Chapter {chapter.ordinal}",
            text=evidence.excerpt,
            start_offset=evidence.start_offset,
            end_offset=evidence.end_offset,
        ))
    return grouped


def _entity_name(entity_id: uuid.UUID, entities: dict[uuid.UUID, Entity]) -> str:
    try:
        return entities[canonical_id(entity_id, entities)].canonical_name
    except (KeyError, ResolutionConflict):
        return "Unknown entity"


@router.post(
    "/structured-memory/run",
    response_model=MemoryRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_memory(
    project_id: uuid.UUID, payload: MemoryStart, session: Session,
) -> MemoryRunRead | JSONResponse:
    try:
        version = await current_scope(
            session, project_id, payload.manuscript_version_id, lock=True
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ResolutionConflict as exc:
        raise HTTPException(409, str(exc)) from None
    resolution_done = await session.scalar(select(JobRun.id).where(
        JobRun.job_type == "entity_resolution",
        JobRun.project_id == project_id,
        JobRun.manuscript_version_id == version.id,
        JobRun.status == "completed",
    ).limit(1))
    if resolution_done is None:
        raise HTTPException(409, "Resolve manuscript entities before building story memory")

    state_hash = await resolution_state_hash(session, version.id)
    base_key = f"structured-memory:{version.id}:{PROMPT_VERSION}:{state_hash}"
    jobs = list(await session.scalars(select(JobRun).where(
        JobRun.job_type == "structured_memory",
        JobRun.project_id == project_id,
        JobRun.manuscript_version_id == version.id,
        JobRun.idempotency_key.like(f"{base_key}%"),
    ).order_by(JobRun.created_at.desc(), JobRun.id.desc())))
    active = next((item for item in jobs if item.status in {"queued", "running"}), None)
    successful = next(
        (item for item in jobs if item.status == "completed" and item.error_code is None),
        None,
    )
    reusable = (
        successful
        if successful and jobs[0].id == successful.id and not payload.rebuild
        else None
    )
    if active or reusable:
        job = active or reusable
        return MemoryRunRead(
            job_id=job.id, manuscript_version_id=version.id, status=job.status
        )

    key = base_key if not jobs else f"{base_key}:retry:{len(jobs) + 1}"
    job = JobRun(
        job_type="structured_memory",
        project_id=project_id,
        manuscript_version_id=version.id,
        idempotency_key=key,
        stage="queued",
    )
    queued_at = datetime.now(timezone.utc)
    job.stage_started_at = queued_at
    session.add(job)
    await session.commit()
    await session.refresh(job)
    try:
        await build_structured_memory.kiq(str(job.id))
    except Exception:
        await session.refresh(job, with_for_update=True)
        if job.status != "queued" or job.stage_started_at != queued_at:
            return MemoryRunRead(
                job_id=job.id, manuscript_version_id=version.id, status=job.status
            )
        job.status = "failed"
        job.error_code = "QUEUE_UNAVAILABLE"
        job.error_message_safe = "Story memory could not be queued."
        job.completed_at = datetime.now(timezone.utc)
        await session.commit()
        return JSONResponse(status_code=503, content={
            "error": {"code": job.error_code, "message": job.error_message_safe}
        })
    return MemoryRunRead(
        job_id=job.id, manuscript_version_id=version.id, status=job.status
    )


@router.get("/structured-memory/status", response_model=MemoryStatusRead)
async def memory_status(project_id: uuid.UUID, session: Session) -> MemoryStatusRead:
    version_id = await _current_version_id(project_id, session)
    if version_id is None:
        return MemoryStatusRead(manuscript_version_id=None, job=None)
    job = await _latest_job(session, project_id, version_id)
    if job is None:
        return MemoryStatusRead(manuscript_version_id=version_id, job=None)
    completed, failed = (await session.execute(select(
        func.count().filter(MemoryChunkResult.status == "completed"),
        func.count().filter(MemoryChunkResult.status == "failed"),
    ).where(MemoryChunkResult.job_id == job.id))).one()
    counts = []
    for model in (Fact, Event, Relationship):
        counts.append(await session.scalar(
            select(func.count()).select_from(model).where(model.job_id == job.id)
        ) or 0)
    return MemoryStatusRead(
        manuscript_version_id=version_id,
        job=await get_job(job.id, session),
        completed_chunks=completed,
        failed_chunks=failed,
        total_chunks=job.total_units or 0,
        facts=counts[0],
        events=counts[1],
        relationships=counts[2],
    )


@router.get("/facts", response_model=list[FactRead])
async def list_facts(project_id: uuid.UUID, session: Session) -> list[FactRead]:
    version_id = await _current_version_id(project_id, session)
    job = await _latest_job(
        session, project_id, version_id, completed=True
    ) if version_id else None
    if job is None:
        return []
    facts = list(await session.scalars(select(Fact).where(
        Fact.job_id == job.id, Fact.status == "active"
    ).order_by(Fact.created_at, Fact.id)))
    evidence = await _evidence_map(
        session, FactEvidence, FactEvidence.fact_id, [item.id for item in facts]
    )
    return [FactRead(
        id=item.id,
        subject=item.subject_text,
        predicate=item.predicate,
        value=item.object_text,
        fact_type=item.fact_type,
        confidence=item.confidence,
        source=evidence[item.id][0].chapter if evidence[item.id] else None,
        status=item.status,
        evidence=evidence[item.id],
    ) for item in facts]


@router.get("/events", response_model=list[EventRead])
async def list_events(project_id: uuid.UUID, session: Session) -> list[EventRead]:
    version_id = await _current_version_id(project_id, session)
    job = await _latest_job(
        session, project_id, version_id, completed=True
    ) if version_id else None
    if job is None:
        return []
    events = list(await session.scalars(select(Event).where(
        Event.job_id == job.id
    ).order_by(Event.narrative_chapter_ordinal, Event.created_at, Event.id)))
    ids = [item.id for item in events]
    evidence = await _evidence_map(session, EventEvidence, EventEvidence.event_id, ids)
    events.sort(key=lambda item: (
        item.narrative_chapter_ordinal,
        evidence[item.id][0].start_offset if evidence[item.id] else float("inf"),
        str(item.id),
    ))
    entities = await entity_map(session, version_id)
    participants, locations = defaultdict(list), defaultdict(list)
    if ids:
        for event_id, entity_id in (await session.execute(select(
            EventParticipant.event_id, EventParticipant.entity_id
        ).where(EventParticipant.event_id.in_(ids)))).all():
            participants[event_id].append(_entity_name(entity_id, entities))
        for event_id, entity_id in (await session.execute(select(
            EventLocation.event_id, EventLocation.entity_id
        ).where(EventLocation.event_id.in_(ids)))).all():
            locations[event_id].append(_entity_name(entity_id, entities))
    return [EventRead(
        id=item.id,
        type=item.event_type,
        title=item.description,
        description=item.description,
        chronological_time=item.chronological_time_raw,
        chronological_time_normalized=item.chronological_time_normalized,
        narrative_position=f"Chapter {item.narrative_chapter_ordinal}",
        chapter=f"Chapter {item.narrative_chapter_ordinal}",
        location=sorted(locations[item.id])[0] if locations[item.id] else None,
        participants=sorted(participants[item.id]),
        evidence=evidence[item.id],
    ) for item in events]


@router.get("/relationships", response_model=list[RelationshipRead])
async def list_relationships(
    project_id: uuid.UUID, session: Session,
) -> list[RelationshipRead]:
    version_id = await _current_version_id(project_id, session)
    job = await _latest_job(
        session, project_id, version_id, completed=True
    ) if version_id else None
    if job is None:
        return []
    relationships = list(await session.scalars(select(Relationship).where(
        Relationship.job_id == job.id
    ).order_by(Relationship.created_at, Relationship.id)))
    evidence = await _evidence_map(
        session,
        RelationshipEvidence,
        RelationshipEvidence.relationship_id,
        [item.id for item in relationships],
    )
    entities = await entity_map(session, version_id)
    result = []
    for item in relationships:
        source = _entity_name(item.source_entity_id, entities)
        target = _entity_name(item.target_entity_id, entities)
        result.append(RelationshipRead(
            id=item.id,
            name=f"{source} — {item.relation_type.replace('_', ' ')} — {target}",
            type=item.relation_type,
            source=source,
            target=target,
            status=item.status,
            start_event_id=item.start_event_id,
            end_event_id=item.end_event_id,
            evidence=evidence[item.id],
        ))
    return result
