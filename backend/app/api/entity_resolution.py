import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.entity_resolution import PROMPT_VERSION
from app.ai.entity_extraction import EntityType
from app.api.ingestion import _current_version_id, get_job
from app.db.models.entity_resolution import EntityAlias, ResolutionCandidate
from app.db.models.job_run import JobRun
from app.db.models.project import Project
from app.db.session import get_session
from app.entity_resolution import (
    MAX_CANDIDATES, ResolutionConflict, apply_decision, candidates_for, canonical_id,
    current_scope, entity_map, evidence_for, make_pair, needs_evaluation,
    normalize_name, resolution_config, resolution_counts, source_rows,
)
from app.queue.tasks.ingestion import _finish_stage
from app.queue.tasks.entity_resolution import resolve_manuscript_entities
from app.schemas.entity_resolution import (
    EntityRead, ResolutionAction, ResolutionCandidatesRead,
    ResolutionRunRead, ResolutionStart,
)

router = APIRouter(prefix="/api/projects/{project_id}", tags=["entity-resolution"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/entity-resolution/run", response_model=ResolutionRunRead, status_code=202)
async def start_resolution(project_id: uuid.UUID, payload: ResolutionStart, session: Session):
    try:
        version = await current_scope(session, project_id, payload.manuscript_version_id, lock=True)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ResolutionConflict as exc:
        raise HTTPException(409, str(exc)) from None
    key = f"entity-resolution:{version.id}:{PROMPT_VERSION}"
    job = await session.scalar(select(JobRun).where(JobRun.idempotency_key == key))
    if job is not None:
        candidates = await candidates_for(session, version.id)
        pending = any(needs_evaluation(item) for item in candidates)
        if job.status in {"queued", "running"} or (job.status == "completed" and not pending):
            return ResolutionRunRead(job_id=job.id, manuscript_version_id=version.id, status=job.status)
        job.status = "queued"
        job.stage = "queued"
        job.completed_at = None
        job.error_code = job.error_message_safe = None
    else:
        job = JobRun(job_type="entity_resolution", project_id=project_id,
                     manuscript_version_id=version.id, idempotency_key=key, stage="queued")
        session.add(job)
    queued_at = datetime.now(timezone.utc)
    job.stage_started_at = queued_at
    await session.commit()
    await session.refresh(job)
    try:
        await resolve_manuscript_entities.kiq(str(job.id))
    except Exception:
        await session.refresh(job, with_for_update=True)
        if job.status != "queued" or job.stage_started_at != queued_at:
            # A late enqueue failure must not undo Stop or affect a newer Resume.
            return ResolutionRunRead(job_id=job.id, manuscript_version_id=version.id, status=job.status)
        job.status = "failed"
        job.error_code = "QUEUE_UNAVAILABLE"
        job.error_message_safe = "Entity resolution could not be queued."
        await session.commit()
        return JSONResponse(status_code=503, content={"error": {"code": job.error_code, "message": job.error_message_safe}})
    return ResolutionRunRead(job_id=job.id, manuscript_version_id=version.id, status=job.status)


@router.post("/entity-resolution/jobs/{job_id}/stop", response_model=ResolutionRunRead)
async def stop_resolution(project_id: uuid.UUID, job_id: uuid.UUID, payload: ResolutionStart, session: Session):
    # Serialize with start/persistence; only this project's version-pinned job is stopped.
    project = await session.get(Project, project_id, with_for_update=True)
    if project is None:
        raise HTTPException(404, "Project not found")
    job = await session.scalar(select(JobRun).where(
        JobRun.id == job_id, JobRun.project_id == project_id,
        JobRun.manuscript_version_id == payload.manuscript_version_id,
        JobRun.job_type == "entity_resolution",
    ).with_for_update())
    if job is None:
        raise HTTPException(404, "Resolution job not found")
    if job.status not in {"queued", "running", "cancelled"}:
        raise HTTPException(409, "Resolution is no longer running")
    if job.status != "cancelled":
        now = datetime.now(timezone.utc)
        _finish_stage(job, now)
        job.status = "cancelled"
        job.completed_at = now
        job.error_code = "USER_CANCELLED"
        job.error_message_safe = "Resolution stopped. Saved decisions are preserved; resume to continue."
        await session.commit()
    return ResolutionRunRead(job_id=job.id, manuscript_version_id=job.manuscript_version_id, status=job.status)


@router.get("/entity-resolution/candidates", response_model=ResolutionCandidatesRead)
async def list_candidates(
    project_id: uuid.UUID, session: Session,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    version_id = await _current_version_id(project_id, session)
    config = resolution_config()
    candidates = await candidates_for(session, version_id) if version_id else []
    sources = {mention.id: (mention, chapter) for mention, chapter in await source_rows(session, version_id)} if version_id else {}
    entities = await entity_map(session, version_id) if version_id else {}
    visible = [item for item in candidates if not item.applied_decision]
    items = []
    for candidate in visible[offset:offset + limit]:
        pair = make_pair(candidate, sources)
        def side(mention_id):
            mention = sources[mention_id][0]
            return {"id": mention.entity_id, "name": mention.surface_text, "type": mention.entity_type,
                    "canonical_id": canonical_id(mention.entity_id, entities)}
        items.append({"id": candidate.id, "left": side(candidate.left_mention_id),
                      "right": side(candidate.right_mention_id), "llm_decision": candidate.llm_decision,
                      "applied_decision": candidate.applied_decision, "error_code": candidate.error_code,
                      "latency_ms": candidate.model_metadata.get("latency_ms"),
                      "trace_id": candidate.model_metadata.get("trace_id"),
                      "attempt": candidate.model_metadata.get("attempt", 1 if candidate.error_code or candidate.llm_decision else 0),
                      "timeout_seconds": candidate.model_metadata.get("timeout_seconds"),
                      "http_status": candidate.model_metadata.get("http_status"),
                      "evidence": list(pair.evidence)})
    job = await session.scalar(select(JobRun).where(
        JobRun.project_id == project_id, JobRun.manuscript_version_id == version_id,
        JobRun.job_type == "entity_resolution",
    ).order_by(JobRun.created_at.desc()).limit(1)) if version_id else None
    return ResolutionCandidatesRead(
        manuscript_version_id=version_id, items=items, total=len(visible),
        **resolution_counts(candidates),
        request_timeout_seconds=config.get("request_timeout_seconds", 180),
        offset=offset, limit=limit, candidate_limit_reached=len(candidates) >= MAX_CANDIDATES,
        auto_apply=config.get("auto_apply") is True, model=config["provider_model"],
        pipeline=config.get("pipeline", "gemma"),
        job=await get_job(job.id, session) if job else None,
    )


@router.post("/entity-resolution/{candidate_id}/resolve", status_code=204)
async def resolve_candidate(project_id: uuid.UUID, candidate_id: uuid.UUID, payload: ResolutionAction, session: Session):
    try:
        version = await current_scope(session, project_id, lock=True)
        candidate = await session.scalar(select(ResolutionCandidate).where(
            ResolutionCandidate.id == candidate_id, ResolutionCandidate.manuscript_version_id == version.id,
        ).with_for_update())
        if candidate is None:
            raise LookupError("Candidate not found in the current manuscript")
        await apply_decision(session, candidate, payload.decision)
        await session.commit()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ResolutionConflict as exc:
        raise HTTPException(409, str(exc)) from None
    return Response(status_code=204)


async def _entities_of_type(session: AsyncSession, version_id: uuid.UUID | None, entity_type: EntityType = EntityType.CHARACTER):
    if version_id is None:
        return {}, {}, {}
    entities = await entity_map(session, version_id)
    aliases = {}
    for alias in await session.scalars(select(EntityAlias).where(EntityAlias.entity_id.in_(entities))):
        root = canonical_id(alias.entity_id, entities)
        if normalize_name(alias.alias) != normalize_name(entities[root].canonical_name):
            aliases.setdefault(root, set()).add(alias.alias)
    characters = {key: entity for key, entity in entities.items() if entity.entity_type == entity_type and entity.merged_into_id is None}
    return characters, aliases, entities


@router.get("/characters", response_model=list[EntityRead])
async def list_characters(project_id: uuid.UUID, session: Session):
    return await list_entities(project_id, session, EntityType.CHARACTER)


@router.get("/locations", response_model=list[EntityRead])
async def list_locations(project_id: uuid.UUID, session: Session):
    return await list_entities(project_id, session, EntityType.LOCATION)


@router.get("/entities", response_model=list[EntityRead])
async def list_entities(project_id: uuid.UUID, session: Session, type: EntityType = EntityType.CHARACTER):
    version_id = await _current_version_id(project_id, session)
    characters, aliases, _ = await _entities_of_type(session, version_id, type)
    return [EntityRead(id=key, name=entity.canonical_name, type=entity.entity_type,
                          status=entity.status, aliases=sorted(aliases.get(key, set())))
            for key, entity in sorted(characters.items(), key=lambda item: (item[1].canonical_name.casefold(), str(item[0])))]


@router.get("/characters/{entity_id}", response_model=EntityRead)
async def get_character(project_id: uuid.UUID, entity_id: uuid.UUID, session: Session):
    return await get_entity(project_id, entity_id, session, EntityType.CHARACTER)


@router.get("/entities/{entity_id}", response_model=EntityRead)
async def get_entity(project_id: uuid.UUID, entity_id: uuid.UUID, session: Session, type: EntityType | None = None):
    version_id = await _current_version_id(project_id, session)
    entities = await entity_map(session, version_id) if version_id else {}
    if entity_id not in entities or (type is not None and entities[entity_id].entity_type != type):
        raise HTTPException(404, "Entity not found in the current manuscript")
    characters, aliases, entities = await _entities_of_type(session, version_id, EntityType(entities[entity_id].entity_type))
    root = canonical_id(entity_id, entities)
    entity = characters[root]
    evidence = {}
    for mention, chapter in await source_rows(session, version_id):
        if mention.entity_id in entities and canonical_id(mention.entity_id, entities) == root:
            item = evidence_for(mention, chapter)
            evidence[item["id"]] = item
            if len(evidence) >= 20:
                break
    return EntityRead(id=root, name=entity.canonical_name, type=entity.entity_type, status=entity.status,
                         aliases=sorted(aliases.get(root, set())), evidence=list(evidence.values()))
