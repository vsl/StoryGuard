"""Version-scoped resolution. Inference never runs while a DB transaction is open."""

import hashlib
import uuid
from collections import defaultdict, deque
from dataclasses import asdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.entity_resolution import (
    PROMPT_HASH, PROMPT_VERSION, MentionRef, ResolutionInput,
    ResolutionResult, normalize_name,
)
from app.ai.extraction_models import resolution_model_config
from app.db.models.entity_mention import EntityMention
from app.db.models.entity_resolution import Entity, EntityAlias, ResolutionCandidate, ResolutionDecision
from app.db.models.manuscript_version import ManuscriptVersion
from app.db.models.narrative import Chapter
from app.db.models.project import Project


MAX_CANDIDATES = 2000
MAX_CALLS_PER_RUN = 20
RUN_BUDGET_SECONDS = 300
CONTEXT_RADIUS = 500
RETRYABLE_ERRORS = {"MODEL_UNAVAILABLE", "MODEL_TIMEOUT", "MODEL_CONNECTION_ERROR", "MODEL_RATE_LIMITED", "MODEL_SERVER_ERROR"}


def needs_evaluation(candidate: ResolutionCandidate) -> bool:
    # A retriable provider error gets its initial request plus one retry. Without
    # this persistent cap, automatically queued batches could retry it forever.
    retryable = (
        candidate.error_code in RETRYABLE_ERRORS
        and candidate.model_metadata.get("attempt", 0) < 2
    )
    untouched = candidate.llm_decision is None and candidate.error_code is None
    return candidate.applied_decision is None and (retryable or untouched)


def resolution_counts(candidates: list[ResolutionCandidate]) -> dict:
    return {
        "remaining": sum(needs_evaluation(item) for item in candidates),
        "review_count": sum(not item.applied_decision and bool(item.llm_decision) and item.error_code in {None, "CLUSTER_CONFLICT"} for item in candidates),
        "error_count": sum(not item.applied_decision and item.error_code not in {None, "CLUSTER_CONFLICT"} for item in candidates),
        "successful_count": sum(bool(item.applied_decision) or (bool(item.llm_decision) and not item.error_code) for item in candidates),
        "applied_count": sum(bool(item.applied_decision) for item in candidates),
        "coreference_merge_count": sum(item.applied_decision == "merge" and item.model_metadata.get("resolver") == "coreference" for item in candidates),
        "gemma_comparison_count": sum(item.model_metadata.get("resolver") == "gemma" for item in candidates),
    }


class ResolutionConflict(ValueError):
    pass


def resolution_config() -> dict:
    config = resolution_model_config()
    if config.get("pipeline", "gemma") not in {"gemma", "coreference_gemma"}:
        raise ValueError("Unknown resolution pipeline")
    timeout = config.get("request_timeout_seconds", 180)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 600:
        raise ValueError("Resolution request timeout must be between 1 and 600 seconds")
    max_output_tokens = config.get("max_output_tokens")
    if isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int) or not 1 <= max_output_tokens <= 8192:
        raise ValueError("Resolution max output tokens must be between 1 and 8192")
    return config


async def current_scope(
    session: AsyncSession, project_id: uuid.UUID,
    expected_version_id: uuid.UUID | None = None, *, lock: bool = False,
) -> ManuscriptVersion:
    project = await session.get(Project, project_id, with_for_update=lock)
    if project is None:
        raise LookupError("Project not found")
    if project.current_manuscript_version_id is None:
        raise ResolutionConflict("A ready manuscript version is required")
    version = await session.get(
        ManuscriptVersion, project.current_manuscript_version_id, with_for_update=lock
    )
    if (
        version is None or version.project_id != project_id or version.status != "ready"
        or (expected_version_id is not None and version.id != expected_version_id)
    ):
        raise ResolutionConflict("The current manuscript version changed or is not ready")
    return version


async def source_rows(session: AsyncSession, version_id: uuid.UUID) -> list:
    return list((await session.execute(
        select(EntityMention, Chapter)
        .join(Chapter, EntityMention.chapter_id == Chapter.id)
        .where(EntityMention.manuscript_version_id == version_id, Chapter.manuscript_version_id == version_id)
        .order_by(Chapter.ordinal, EntityMention.start_offset, EntityMention.id)
    )).all())


def candidate_pairs(mentions: list[EntityMention]) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Names only BLOCK candidates; they never establish identity."""
    by_token: dict[tuple[str, str], deque] = defaultdict(lambda: deque(maxlen=3))
    nearby: dict[str, deque] = defaultdict(lambda: deque(maxlen=3))
    pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for mention in mentions:
        tokens = set(normalize_name(mention.surface_text).split()) - {"mr", "mrs", "ms", "dr"}
        candidates = {}
        for token in sorted(tokens):
            for previous in by_token[(mention.entity_type, token)]:
                candidates[previous.id] = previous
        for previous in nearby[mention.entity_type]:
            if previous.chapter_id == mention.chapter_id and mention.start_offset - previous.end_offset <= CONTEXT_RADIUS:
                candidates[previous.id] = previous
        # ponytail: bounded lexical/local candidates can miss distant aliases;
        # measure candidate recall before adding semantic candidate retrieval.
        for previous in sorted(candidates.values(), key=lambda item: (
            normalize_name(item.surface_text) != normalize_name(mention.surface_text),
            str(item.id),
        ))[:6]:
            pairs.add(tuple(sorted((previous.id, mention.id))))
            if len(pairs) >= MAX_CANDIDATES:
                return sorted(pairs)
        for token in sorted(tokens):
            by_token[(mention.entity_type, token)].append(mention)
        nearby[mention.entity_type].append(mention)
    return sorted(pairs)


def evidence_for(mention: EntityMention, chapter: Chapter) -> dict:
    if (
        mention.manuscript_version_id != chapter.manuscript_version_id
        or mention.chapter_id != chapter.id
        or mention.start_offset < 0 or mention.end_offset > len(chapter.text)
        or chapter.text[mention.start_offset:mention.end_offset] != mention.surface_text
    ):
        raise ResolutionConflict("The source mention no longer matches its manuscript")
    start = max(0, mention.start_offset - CONTEXT_RADIUS)
    end = min(len(chapter.text), mention.end_offset + CONTEXT_RADIUS)
    excerpt = chapter.text[start:end]
    digest = hashlib.sha256(excerpt.encode()).hexdigest()
    evidence_id = uuid.uuid5(mention.manuscript_version_id, f"resolution:{chapter.id}:{start}:{end}:{digest}")
    return {
        "id": str(evidence_id), "manuscript_version_id": str(mention.manuscript_version_id),
        "chapter_id": str(chapter.id), "chapter": chapter.title or f"Chapter {chapter.ordinal}",
        "start_offset": start, "end_offset": end, "text": excerpt,
    }


def make_pair(candidate: ResolutionCandidate, sources: dict) -> ResolutionInput:
    try:
        left, left_chapter = sources[candidate.left_mention_id]
        right, right_chapter = sources[candidate.right_mention_id]
    except KeyError:
        raise ResolutionConflict("Candidate source mentions are no longer available") from None
    if (
        left.manuscript_version_id != candidate.manuscript_version_id
        or right.manuscript_version_id != candidate.manuscript_version_id
        or left.entity_type != right.entity_type
    ):
        raise ResolutionConflict("Candidate source scope does not match")
    left_evidence, right_evidence = evidence_for(left, left_chapter), evidence_for(right, right_chapter)
    def reference(mention, evidence):
        return MentionRef(str(mention.id), mention.surface_text, mention.entity_type,
                          evidence["id"], mention.start_offset, mention.end_offset)
    evidence = {item["id"]: item for item in (left_evidence, right_evidence)}
    return ResolutionInput(reference(left, left_evidence), reference(right, right_evidence), tuple(evidence.values()))


async def prepare_candidates(session: AsyncSession, version_id: uuid.UUID) -> int:
    rows = await source_rows(session, version_id)
    mentions = [mention for mention, _ in rows]
    for mention, chapter in rows:
        evidence_for(mention, chapter)
    entities = await entity_map(session, version_id)
    new_mentions = [mention for mention in mentions if mention.entity_id is None]
    new_ids = {mention.id for mention in new_mentions}
    session.add_all([Entity(id=mention.id, manuscript_version_id=version_id,
                           entity_type=mention.entity_type, canonical_name=mention.surface_text)
                     for mention in new_mentions])
    await session.flush()
    for mention in new_mentions:
        mention.entity_id = mention.id
        session.add(EntityAlias(entity_id=mention.id, alias=mention.surface_text,
                                normalized_alias=normalize_name(mention.surface_text)))
    for mention in mentions:
        if mention.id not in new_ids and mention.entity_id not in entities:
            raise ResolutionConflict("An identity anchor belongs to another manuscript")
    await session.flush()
    existing = set((await session.execute(
        select(ResolutionCandidate.left_mention_id, ResolutionCandidate.right_mention_id)
        .where(ResolutionCandidate.manuscript_version_id == version_id)
    )).all())
    for left, right in candidate_pairs(mentions):
        if (left, right) not in existing:
            session.add(ResolutionCandidate(manuscript_version_id=version_id,
                                            left_mention_id=left, right_mention_id=right))
    await session.flush()
    return len(mentions)


async def entity_map(session: AsyncSession, version_id: uuid.UUID) -> dict[uuid.UUID, Entity]:
    return {entity.id: entity for entity in await session.scalars(
        select(Entity).where(Entity.manuscript_version_id == version_id)
    )}


def canonical_id(entity_id: uuid.UUID, entities: dict[uuid.UUID, Entity]) -> uuid.UUID:
    visited = set()
    while True:
        if entity_id in visited or entity_id not in entities:
            raise ResolutionConflict("Invalid identity link chain")
        visited.add(entity_id)
        parent = entities[entity_id].merged_into_id
        if parent is None:
            return entity_id
        entity_id = parent


async def candidates_for(session: AsyncSession, version_id: uuid.UUID) -> list[ResolutionCandidate]:
    return list(await session.scalars(
        select(ResolutionCandidate).where(ResolutionCandidate.manuscript_version_id == version_id)
        .order_by(ResolutionCandidate.created_at, ResolutionCandidate.id)
    ))


def decision_snapshot(left: uuid.UUID, right: uuid.UUID, entities: dict) -> dict:
    return {
        "left_root": str(left), "right_root": str(right),
        "entities": {str(key): {"merged_into_id": str(entities[key].merged_into_id) if entities[key].merged_into_id else None,
                               "status": entities[key].status} for key in {left, right}},
    }


async def apply_decision(
    session: AsyncSession, candidate: ResolutionCandidate, decision: str, *, source: str = "human",
) -> None:
    if decision not in {"merge", "keep_separate"} or source not in {"human", "automatic"}:
        raise ValueError("Invalid applied decision")
    if candidate.applied_decision is not None:
        if candidate.applied_decision == decision:
            return
        raise ResolutionConflict("This candidate already has a different applied decision")
    sources = {mention.id: (mention, chapter) for mention, chapter in await source_rows(session, candidate.manuscript_version_id)}
    pair = make_pair(candidate, sources)
    entities = await entity_map(session, candidate.manuscript_version_id)
    left = canonical_id(sources[candidate.left_mention_id][0].entity_id, entities)
    right = canonical_id(sources[candidate.right_mention_id][0].entity_id, entities)
    if decision == "keep_separate" and left == right:
        raise ResolutionConflict("These mentions are already linked; undo is required before separating them")
    if decision == "merge":
        for other in await candidates_for(session, candidate.manuscript_version_id):
            if other.applied_decision != "keep_separate":
                continue
            a = canonical_id(sources[other.left_mention_id][0].entity_id, entities)
            b = canonical_id(sources[other.right_mention_id][0].entity_id, entities)
            if a != b and {a, b} <= {left, right}:
                raise ResolutionConflict("Merge conflicts with an existing keep-separate decision")
    before = decision_snapshot(left, right, entities)
    if decision == "merge" and left != right:
        target, retired = sorted((entities[left], entities[right]), key=lambda entity: (-len(entity.canonical_name), str(entity.id)))
        retired.merged_into_id = target.id
        retired.status = "merged"
        target.status = "active"
    elif decision == "keep_separate":
        entities[left].status = entities[right].status = "active"
    candidate.applied_decision = decision
    session.add(ResolutionDecision(
        manuscript_version_id=candidate.manuscript_version_id, candidate_id=candidate.id,
        decision=decision, source=source, evidence=list(pair.evidence),
        before=before, after=decision_snapshot(left, right, entities),
        model_metadata=candidate.model_metadata if source == "automatic" else {},
    ))
    # Original mentions and aliases stay on their identity anchors. Reversing
    # audited links in reverse decision order reconstructs the prior assignments.
    await session.flush()


async def save_prediction(
    session: AsyncSession, candidate: ResolutionCandidate, original_pair: ResolutionInput,
    result: ResolutionResult | None, error_code: str | None = None,
    *, diagnostics: dict | None = None,
) -> None:
    sources = {mention.id: (mention, chapter) for mention, chapter in await source_rows(session, candidate.manuscript_version_id)}
    if asdict(make_pair(candidate, sources)) != asdict(original_pair):
        raise ResolutionConflict("Candidate evidence changed during inference")
    if not needs_evaluation(candidate):
        return
    attempt = 1 + (await session.scalar(select(func.max(ResolutionDecision.attempt)).where(
        ResolutionDecision.candidate_id == candidate.id, ResolutionDecision.source == "model",
    )) or 0)
    candidate.llm_decision = result.output.decision if result else None
    candidate.evidence_ids = result.output.evidence_ids if result else []
    candidate.error_code = error_code
    candidate.model_metadata = {
        "prompt_version": PROMPT_VERSION, "prompt_hash": PROMPT_HASH,
        "model_alias": resolution_config()["litellm_alias"],
        "configured_model": resolution_config()["provider_model"],
        "model_digest": resolution_config().get("digest"),
        "resolved_model": result.model if result else None,
        "latency_ms": result.latency_ms if result else None,
        "repair_count": result.repair_count if result else None,
        "usage": result.usage if result else {}, "trace_id": result.trace_id if result else None,
        "error_code": error_code,
        **(diagnostics or {}),
        "attempt": attempt,
    }
    session.add(ResolutionDecision(
        manuscript_version_id=candidate.manuscript_version_id, candidate_id=candidate.id,
        decision=candidate.llm_decision, source="model", attempt=attempt, evidence=list(original_pair.evidence),
        before={}, after={"recommendation": candidate.llm_decision, "applied": False},
        model_metadata=candidate.model_metadata,
    ))
    await session.flush()


async def apply_automatic_predictions(session: AsyncSession, version_id: uuid.UUID) -> None:
    if resolution_config().get("auto_apply") is not True:
        return
    entities = await entity_map(session, version_id)
    sources = {mention.id: mention for mention, _ in await source_rows(session, version_id)}
    candidates = await candidates_for(session, version_id)
    parents = {key: canonical_id(key, entities) for key in entities}
    def root(key):
        while parents[key] != key:
            key = parents[key]
        return key
    def ends(candidate):
        return (sources[candidate.left_mention_id].entity_id, sources[candidate.right_mention_id].entity_id)
    proposals = [item for item in candidates if item.llm_decision == "merge" and not item.applied_decision and not item.error_code]
    for candidate in proposals:
        a, b = (root(key) for key in ends(candidate))
        parents[a] = b
    # Check the complete proposed component, not only the next edge: A=B, B=C,
    # A!=C must leave both proposed merges unapplied.
    conflicts = set()
    for candidate in candidates:
        if candidate.applied_decision == "keep_separate" or (not candidate.applied_decision and candidate.llm_decision == "keep_separate" and not candidate.error_code):
            a, b = (root(key) for key in ends(candidate))
            if a == b:
                conflicts.add(a)
    for candidate in candidates:
        if candidate.applied_decision or candidate.llm_decision not in {"merge", "keep_separate"} or candidate.error_code:
            continue
        if candidate.llm_decision == "merge" and root(ends(candidate)[0]) in conflicts:
            candidate.error_code = "CLUSTER_CONFLICT"
            continue
        try:
            await apply_decision(session, candidate, candidate.llm_decision, source="automatic")
        except ResolutionConflict:
            candidate.error_code = "CLUSTER_CONFLICT"
