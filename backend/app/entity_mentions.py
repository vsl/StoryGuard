import uuid

from sqlalchemy import delete, select

from app.ai.entity_extraction import (
    MODEL_ALIAS,
    ChapterMention,
    SourceChunk,
    deduplicate_mentions,
    extract_entities,
    to_chapter_mentions,
)
from app.db.models.entity_mention import EntityMention
from app.db.models.manuscript_version import ManuscriptVersion
from app.db.models.narrative import Chapter, Chunk
from app.db.session import SessionLocal


PROMPT_VERSION = "entity_extractor:v2"


async def extract_version_entities(
    project_id: uuid.UUID, manuscript_version_id: uuid.UUID
) -> int:
    async with SessionLocal() as session:
        version = await session.get(ManuscriptVersion, manuscript_version_id)
        if version is None or version.project_id != project_id:
            raise LookupError("Manuscript version not found in project")
        chunks = list(
            await session.scalars(
                select(Chunk)
                .where(Chunk.manuscript_version_id == manuscript_version_id)
                .order_by(Chunk.ordinal)
            )
        )
        chapter_text = dict(
            (
                await session.execute(
                    select(Chapter.id, Chapter.text).where(
                        Chapter.manuscript_version_id == manuscript_version_id
                    )
                )
            ).all()
        )
    if not chunks:
        raise ValueError("Manuscript version has no chunks")

    extracted: list[ChapterMention] = []
    for chunk in chunks:
        result = await extract_entities(
            chunk.text,
            PROMPT_VERSION,
            model_alias=MODEL_ALIAS,
        )
        extracted.extend(
            to_chapter_mentions(
                SourceChunk(
                    id=str(chunk.id),
                    manuscript_version_id=str(chunk.manuscript_version_id),
                    chapter_id=str(chunk.chapter_id),
                    scene_id=str(chunk.scene_id) if chunk.scene_id else None,
                    start_offset=chunk.start_offset,
                ),
                result.mentions,
            )
        )

    mentions = deduplicate_mentions(extracted)
    if any(
        chapter_text[uuid.UUID(mention.chapter_id)][
            mention.start_offset : mention.end_offset
        ]
        != mention.surface_text
        for mention in mentions
    ):
        raise ValueError("Entity mention does not match chapter evidence")

    async with SessionLocal() as session, session.begin():
        version = await session.get(
            ManuscriptVersion, manuscript_version_id, with_for_update=True
        )
        if version is None or version.project_id != project_id:
            raise LookupError("Manuscript version scope changed during extraction")
        current_chunk_ids = set(
            await session.scalars(
                select(Chunk.id).where(
                    Chunk.manuscript_version_id == manuscript_version_id
                )
            )
        )
        if current_chunk_ids != {chunk.id for chunk in chunks}:
            raise ValueError("Manuscript chunks changed during extraction")
        await session.execute(
            delete(EntityMention).where(
                EntityMention.manuscript_version_id == manuscript_version_id
            )
        )
        session.add_all(
            [
                EntityMention(
                    manuscript_version_id=manuscript_version_id,
                    chapter_id=uuid.UUID(mention.chapter_id),
                    scene_id=(
                        uuid.UUID(mention.scene_id) if mention.scene_id else None
                    ),
                    chunk_id=uuid.UUID(mention.chunk_id),
                    entity_type=mention.entity_type.value,
                    surface_text=mention.surface_text,
                    start_offset=mention.start_offset,
                    end_offset=mention.end_offset,
                    prompt_version=PROMPT_VERSION,
                    model_alias=MODEL_ALIAS,
                )
                for mention in mentions
            ]
        )
    return len(mentions)
