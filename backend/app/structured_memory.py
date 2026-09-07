import hashlib
import json
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.entity_resolution import normalize_name
from app.ai.structured_memory import (
    PROMPT_VERSION,
    EntityRef,
    ExtractionInput,
    ExtractionResult,
    chunk_evidence,
)
from app.db.models.entity_mention import EntityMention
from app.db.models.entity_resolution import Entity, EntityAlias
from app.db.models.narrative import Chapter, Chunk
from app.db.models.structured_memory import (
    Event,
    EventEvidence,
    EventLocation,
    EventParticipant,
    Evidence,
    Fact,
    FactEvidence,
    Relationship,
    RelationshipEvidence,
)
from app.entity_resolution import ResolutionConflict, canonical_id, entity_map


class MemoryConflict(ValueError):
    pass


@dataclass(frozen=True)
class ChunkInput:
    chunk: Chunk
    chapter_ordinal: int
    extraction: ExtractionInput


@dataclass
class RelationshipState:
    id: uuid.UUID
    status: str
    start_event_id: uuid.UUID | None
    end_event_id: uuid.UUID | None


@dataclass
class MemoryIndex:
    facts: dict[tuple, uuid.UUID] = field(default_factory=dict)
    events: dict[tuple, uuid.UUID] = field(default_factory=dict)
    relationships: dict[tuple, RelationshipState] = field(default_factory=dict)
    event_participants: set[tuple[uuid.UUID, uuid.UUID]] = field(default_factory=set)
    event_locations: set[tuple[uuid.UUID, uuid.UUID]] = field(default_factory=set)
    links: set[tuple[str, uuid.UUID, uuid.UUID]] = field(default_factory=set)


def _root(entity_id: uuid.UUID, entities: dict[uuid.UUID, Entity]) -> uuid.UUID:
    try:
        return canonical_id(entity_id, entities)
    except ResolutionConflict as exc:
        raise MemoryConflict("Invalid entity-resolution state") from exc


async def resolution_state_hash(
    session: AsyncSession, manuscript_version_id: uuid.UUID,
) -> str:
    entities = await entity_map(session, manuscript_version_id)
    aliases = list(await session.scalars(
        select(EntityAlias).where(EntityAlias.entity_id.in_(entities))
    )) if entities else []
    mentions = list(await session.scalars(
        select(EntityMention)
        .where(EntityMention.manuscript_version_id == manuscript_version_id)
        .order_by(EntityMention.id)
    ))
    state = {
        "entities": [
            [str(item.id), item.entity_type, item.canonical_name,
             str(item.merged_into_id) if item.merged_into_id else None, item.status]
            for item in sorted(entities.values(), key=lambda value: str(value.id))
        ],
        "aliases": [
            [str(item.entity_id), item.alias, item.normalized_alias]
            for item in sorted(
                aliases,
                key=lambda value: (
                    str(value.entity_id), value.normalized_alias, value.alias,
                ),
            )
        ],
        "mentions": [
            [
                str(item.id),
                str(item.chunk_id),
                str(item.entity_id) if item.entity_id else None,
                item.surface_text,
                item.start_offset,
                item.end_offset,
            ]
            for item in mentions
        ],
    }
    return hashlib.sha256(json.dumps(state, separators=(",", ":")).encode()).hexdigest()[:16]


async def chunk_inputs(
    session: AsyncSession, manuscript_version_id: uuid.UUID,
) -> list[ChunkInput]:
    chunks = list((await session.execute(
        select(Chunk, Chapter.ordinal)
        .join(Chapter, Chunk.chapter_id == Chapter.id)
        .where(
            Chunk.manuscript_version_id == manuscript_version_id,
            Chapter.manuscript_version_id == manuscript_version_id,
        )
        .order_by(Chunk.ordinal)
    )).all())
    if not chunks:
        raise MemoryConflict("Manuscript version has no chunks")
    if any(
        chunk.end_offset != chunk.start_offset + len(chunk.text)
        for chunk, _ in chunks
    ):
        raise MemoryConflict("Chunk evidence no longer matches its source offsets")

    entities = await entity_map(session, manuscript_version_id)
    mention_rows = list((await session.execute(
        select(
            EntityMention.chunk_id,
            EntityMention.entity_id,
            EntityMention.surface_text,
        ).where(EntityMention.manuscript_version_id == manuscript_version_id)
    )).all())
    if any(entity_id is None for _, entity_id, _ in mention_rows):
        raise MemoryConflict("Entity resolution must complete first")

    aliases_by_root: dict[uuid.UUID, set[str]] = {}
    roots_by_chunk: dict[uuid.UUID, set[uuid.UUID]] = {}
    for chunk_id, entity_id, surface_text in mention_rows:
        root = _root(entity_id, entities)
        roots_by_chunk.setdefault(chunk_id, set()).add(root)
        aliases_by_root.setdefault(root, set()).add(surface_text)
    if entities:
        for alias in await session.scalars(
            select(EntityAlias).where(EntityAlias.entity_id.in_(entities))
        ):
            aliases_by_root.setdefault(_root(alias.entity_id, entities), set()).add(alias.alias)

    refs = {
        root: EntityRef(
            id=str(root),
            name=entities[root].canonical_name,
            type=entities[root].entity_type,
            aliases=sorted(
                alias for alias in aliases_by_root.get(root, set())
                if normalize_name(alias) != normalize_name(entities[root].canonical_name)
            )[:50],
        )
        for root in { _root(entity_id, entities) for entity_id in entities }
    }
    return [
        ChunkInput(
            chunk=chunk,
            chapter_ordinal=chapter_ordinal,
            extraction=ExtractionInput(
                evidence=[chunk_evidence(
                    chunk.text,
                    str(manuscript_version_id),
                    str(chunk.chapter_id),
                    str(chunk.id),
                    chunk.start_offset,
                )],
                entities=[refs[root] for root in sorted(
                    roots_by_chunk.get(chunk.id, set()), key=str
                )],
            ),
        )
        for chunk, chapter_ordinal in chunks
    ]


def _fact_key(item) -> tuple:
    return (
        item.subject_entity_id or normalize_name(item.subject_text),
        item.predicate,
        item.object_entity_id or normalize_name(item.object_text),
        item.fact_type,
    )


def _event_key(
    item, participant_entity_ids: set[str], location_entity_ids: set[str],
) -> tuple:
    return (
        item.event_type,
        normalize_name(item.description),
        normalize_name(item.chronological_time_raw or ""),
        tuple(sorted(participant_entity_ids)),
        tuple(sorted(location_entity_ids)),
    )


def _link(index: MemoryIndex, kind: str, owner_id: uuid.UUID, evidence_id: uuid.UUID):
    key = (kind, owner_id, evidence_id)
    if key in index.links:
        return None
    index.links.add(key)
    return {
        "fact": FactEvidence,
        "event": EventEvidence,
        "relationship": RelationshipEvidence,
    }[kind](**{f"{kind}_id": owner_id, "evidence_id": evidence_id})


def _event_participant(
    index: MemoryIndex, event_id: uuid.UUID, entity_id: uuid.UUID,
) -> EventParticipant | None:
    key = (event_id, entity_id)
    if key in index.event_participants:
        return None
    index.event_participants.add(key)
    return EventParticipant(event_id=event_id, entity_id=entity_id)


def _event_location(
    index: MemoryIndex, event_id: uuid.UUID, entity_id: uuid.UUID,
) -> EventLocation | None:
    key = (event_id, entity_id)
    if key in index.event_locations:
        return None
    index.event_locations.add(key)
    return EventLocation(event_id=event_id, entity_id=entity_id)


async def persist_chunk(
    session: AsyncSession,
    job_id: uuid.UUID,
    manuscript_version_id: uuid.UUID,
    source: ChunkInput,
    result: ExtractionResult,
    index: MemoryIndex,
) -> None:
    block = source.extraction.evidence[0]
    evidence_id = uuid.UUID(block.id)
    evidence = await session.get(Evidence, evidence_id)
    if evidence is None:
        evidence = Evidence(
            id=evidence_id,
            manuscript_version_id=manuscript_version_id,
            chapter_id=source.chunk.chapter_id,
            scene_id=source.chunk.scene_id,
            chunk_id=source.chunk.id,
            start_offset=block.start_offset,
            end_offset=block.end_offset,
            excerpt=block.text,
        )
        session.add(evidence)
    elif (
        evidence.manuscript_version_id != manuscript_version_id
        or evidence.chunk_id != source.chunk.id
        or evidence.start_offset != block.start_offset
        or evidence.end_offset != block.end_offset
        or evidence.excerpt != block.text
        ):
        raise MemoryConflict("Evidence source changed")
    # Evidence owns every following citation FK; persist it before association rows.
    await session.flush()

    for item in result.memory.facts:
        key = _fact_key(item)
        fact_id = index.facts.get(key)
        if fact_id is None:
            fact_id = uuid.uuid4()
            index.facts[key] = fact_id
            session.add(Fact(
                id=fact_id,
                job_id=job_id,
                manuscript_version_id=manuscript_version_id,
                subject_entity_id=uuid.UUID(item.subject_entity_id) if item.subject_entity_id else None,
                subject_text=item.subject_text,
                predicate=item.predicate,
                object_entity_id=uuid.UUID(item.object_entity_id) if item.object_entity_id else None,
                object_text=item.object_text,
                fact_type=item.fact_type,
                prompt_version=result.prompt_version,
                model_alias=result.model,
            ))
        link = _link(index, "fact", fact_id, evidence_id)
        if link:
            session.add(link)

    entity_types = {item.id: item.type for item in source.extraction.entities}
    relationship_participants: dict[str, set[str]] = {}
    relationship_locations: dict[str, set[str]] = {}
    for relationship in result.memory.relationships:
        if relationship.event_local_id:
            for entity_id in (
                relationship.source_entity_id, relationship.target_entity_id,
            ):
                entity_type = entity_types.get(entity_id)
                if entity_type in {"character", "organization", "vehicle"}:
                    relationship_participants.setdefault(
                        relationship.event_local_id, set()
                    ).add(entity_id)
                elif entity_type in {"gpe", "location"}:
                    relationship_locations.setdefault(
                        relationship.event_local_id, set()
                    ).add(entity_id)

    local_events: dict[str, uuid.UUID] = {}
    for item in result.memory.events:
        participant_ids = set(item.participant_entity_ids)
        participant_ids.update(relationship_participants.get(item.local_id, set()))
        location_ids = set(item.location_entity_ids)
        location_ids.update(relationship_locations.get(item.local_id, set()))
        key = _event_key(item, participant_ids, location_ids)
        event_id = index.events.get(key)
        if event_id is None:
            event_id = uuid.uuid4()
            index.events[key] = event_id
            session.add(Event(
                id=event_id,
                job_id=job_id,
                manuscript_version_id=manuscript_version_id,
                event_type=item.event_type,
                description=item.description,
                chronological_time_raw=item.chronological_time_raw,
                chronological_time_normalized=item.chronological_time_normalized,
                narrative_chapter_ordinal=source.chapter_ordinal,
                prompt_version=result.prompt_version,
                model_alias=result.model,
            ))
        session.add_all(filter(None, (
            _event_participant(index, event_id, uuid.UUID(entity_id))
            for entity_id in participant_ids
        )))
        session.add_all(filter(None, (
            _event_location(index, event_id, uuid.UUID(entity_id))
            for entity_id in location_ids
        )))
        local_events[item.local_id] = event_id
        link = _link(index, "event", event_id, evidence_id)
        if link:
            session.add(link)

    for item in result.memory.relationships:
        source_id = uuid.UUID(item.source_entity_id)
        target_id = uuid.UUID(item.target_entity_id)
        key = (source_id, item.relation_type, target_id)
        state = index.relationships.get(key)
        change_event_id = local_events.get(item.event_local_id) if item.event_local_id else None
        if item.event_local_id and change_event_id is None:
            raise MemoryConflict("Relationship event was not persisted")
        reuse_ended = (
            item.change == "ended" and state is not None
            and state.status == "ended" and state.end_event_id == change_event_id
        )
        if state is None or (state.status == "ended" and not reuse_ended):
            relationship_id = uuid.uuid4()
            state = RelationshipState(
                relationship_id,
                "ended" if item.change == "ended" else "active",
                change_event_id if item.change == "started" else None,
                change_event_id if item.change == "ended" else None,
            )
            index.relationships[key] = state
            session.add(Relationship(
                id=relationship_id,
                job_id=job_id,
                manuscript_version_id=manuscript_version_id,
                source_entity_id=source_id,
                relation_type=item.relation_type,
                target_entity_id=target_id,
                start_event_id=state.start_event_id,
                end_event_id=state.end_event_id,
                status=state.status,
                prompt_version=result.prompt_version,
                model_alias=result.model,
            ))
        elif item.change in {"started", "ended"}:
            row = await session.get(Relationship, state.id)
            if row is None:
                raise MemoryConflict("Relationship state disappeared")
            if item.change == "started" and row.start_event_id is None:
                row.start_event_id = state.start_event_id = change_event_id
            if item.change == "ended":
                row.end_event_id = state.end_event_id = change_event_id
                row.status = state.status = "ended"
        link = _link(index, "relationship", state.id, evidence_id)
        if link:
            session.add(link)

    await session.flush()
