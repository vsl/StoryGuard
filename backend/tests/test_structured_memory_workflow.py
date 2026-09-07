import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch


RUN_DATABASE_TESTS = os.environ.get("RUN_DATABASE_TESTS") == "1"

if RUN_DATABASE_TESTS:
    import httpx
    from sqlalchemy import select

    from app.ai.structured_memory import (
        PROMPT_VERSION,
        ExtractedEvent,
        ExtractedFact,
        ExtractedRelationship,
        ExtractionResult,
        StructuredMemoryError,
        ValidatedMemory,
    )
    from app.db.models.entity_mention import EntityMention
    from app.db.models.entity_resolution import Entity, EntityAlias
    from app.db.models.job_run import JobRun
    from app.db.models.manuscript_version import ManuscriptVersion
    from app.db.models.narrative import Chapter, Chunk
    from app.db.models.project import Project
    from app.db.models.structured_memory import Event
    from app.db.session import SessionLocal, engine
    from app.main import app
    from app.queue.tasks.structured_memory import run_structured_memory_job
    from app.structured_memory import chunk_inputs, resolution_state_hash


@unittest.skipUnless(RUN_DATABASE_TESTS, "set RUN_DATABASE_TESTS=1")
class StructuredMemoryWorkflowTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.project_id, self.other_project_id = uuid.uuid4(), uuid.uuid4()
        self.version_id, self.chapter_id = uuid.uuid4(), uuid.uuid4()
        self.mara_id, self.ilya_id = uuid.uuid4(), uuid.uuid4()
        married = "Mara and Ilya married in June 2020."
        divorced = "Mara and Ilya divorced in March 2024."
        async with SessionLocal() as session:
            project = Project(id=self.project_id, title="Memory story")
            other = Project(id=self.other_project_id, title="Other story")
            version = ManuscriptVersion(
                id=self.version_id,
                project_id=self.project_id,
                version_number=1,
                status="ready",
                object_key=f"test/{self.version_id}",
                original_filename="story.txt",
                mime_type="text/plain",
                file_size=100,
                content_hash="a" * 64,
            )
            session.add_all([project, other])
            await session.flush()
            session.add(version)
            await session.flush()
            project.current_manuscript_version_id = self.version_id
            chapter = Chapter(
                id=self.chapter_id,
                manuscript_version_id=self.version_id,
                ordinal=1,
                title="One",
                text=f"{married}\n{divorced}",
                content_hash="b" * 64,
            )
            session.add(chapter)
            await session.flush()
            first = Chunk(
                manuscript_version_id=self.version_id,
                chapter_id=self.chapter_id,
                ordinal=1,
                text=married,
                start_offset=0,
                end_offset=len(married),
                content_hash="c" * 64,
            )
            second_start = len(married) + 1
            second = Chunk(
                manuscript_version_id=self.version_id,
                chapter_id=self.chapter_id,
                ordinal=2,
                text=divorced,
                start_offset=second_start,
                end_offset=second_start + len(divorced),
                content_hash="d" * 64,
            )
            session.add_all([first, second])
            await session.flush()
            session.add_all([
                Entity(
                    id=self.mara_id,
                    manuscript_version_id=self.version_id,
                    entity_type="character",
                    canonical_name="Mara",
                    status="active",
                ),
                Entity(
                    id=self.ilya_id,
                    manuscript_version_id=self.version_id,
                    entity_type="character",
                    canonical_name="Ilya",
                    status="active",
                ),
            ])
            await session.flush()
            session.add_all([
                EntityAlias(entity_id=self.mara_id, alias="Mara", normalized_alias="mara"),
                EntityAlias(entity_id=self.ilya_id, alias="Ilya", normalized_alias="ilya"),
                EntityMention(
                    entity_id=self.mara_id,
                    manuscript_version_id=self.version_id,
                    chapter_id=self.chapter_id,
                    chunk_id=first.id,
                    entity_type="character",
                    surface_text="Mara",
                    start_offset=0,
                    end_offset=4,
                    prompt_version="test",
                    model_alias="test",
                ),
                EntityMention(
                    entity_id=self.ilya_id,
                    manuscript_version_id=self.version_id,
                    chapter_id=self.chapter_id,
                    chunk_id=first.id,
                    entity_type="character",
                    surface_text="Ilya",
                    start_offset=9,
                    end_offset=13,
                    prompt_version="test",
                    model_alias="test",
                ),
                EntityMention(
                    entity_id=self.mara_id,
                    manuscript_version_id=self.version_id,
                    chapter_id=self.chapter_id,
                    chunk_id=second.id,
                    entity_type="character",
                    surface_text="Mara",
                    start_offset=second_start,
                    end_offset=second_start + 4,
                    prompt_version="test",
                    model_alias="test",
                ),
                EntityMention(
                    entity_id=self.ilya_id,
                    manuscript_version_id=self.version_id,
                    chapter_id=self.chapter_id,
                    chunk_id=second.id,
                    entity_type="character",
                    surface_text="Ilya",
                    start_offset=second_start + 9,
                    end_offset=second_start + 13,
                    prompt_version="test",
                    model_alias="test",
                ),
                JobRun(
                    job_type="entity_resolution",
                    project_id=self.project_id,
                    manuscript_version_id=self.version_id,
                    idempotency_key=f"resolution:{self.version_id}",
                    status="completed",
                    stage="completed",
                ),
            ])
            await session.commit()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )

    async def asyncTearDown(self) -> None:
        async with SessionLocal() as session:
            project = await session.get(Project, self.project_id)
            other = await session.get(Project, self.other_project_id)
            if project:
                await session.delete(project)
            if other:
                await session.delete(other)
            await session.commit()
        await self.client.aclose()
        await engine.dispose()

    def _result(
        self, inputs, *, ended: bool = False, fact: bool = False,
        event_participants: bool = True,
    ):
        evidence_id = inputs.evidence[0].id
        local_id = "divorce" if ended else "wedding"
        change = "ended" if ended else "started"
        event_type = "relationship_ended" if ended else "relationship_started"
        memory = ValidatedMemory(
            facts=(ExtractedFact(
                subject_text="Mara",
                subject_entity_id=str(self.mara_id),
                predicate="occupation",
                object_text="pilot",
                fact_type="role",
                evidence_ids=[evidence_id],
            ),) if fact else (),
            events=(ExtractedEvent(
                local_id=local_id,
                event_type=event_type,
                description="Mara and Ilya divorced" if ended else "Mara and Ilya married",
                chronological_time_raw="March 2024" if ended else "June 2020",
                participant_texts=["Mara", "Ilya"],
                participant_entity_ids=(
                    sorted([str(self.mara_id), str(self.ilya_id)])
                    if event_participants else []
                ),
                evidence_ids=[evidence_id],
            ),),
            relationships=(ExtractedRelationship(
                source_text="Mara",
                source_entity_id=min(str(self.mara_id), str(self.ilya_id)),
                relation_type="spouse_of",
                target_text="Ilya",
                target_entity_id=max(str(self.mara_id), str(self.ilya_id)),
                change=change,
                event_local_id=local_id,
                evidence_ids=[evidence_id],
            ),),
            rejected_count=0,
            rejection_reasons=(),
        )
        return ExtractionResult(memory, "storyguard-fast", PROMPT_VERSION, 5, 0, {}, 3)

    async def _start(self) -> dict:
        with patch(
            "app.api.structured_memory.build_structured_memory.kiq", new=AsyncMock()
        ):
            response = await self.client.post(
                f"/api/projects/{self.project_id}/structured-memory/run",
                json={"manuscript_version_id": str(self.version_id)},
            )
        self.assertEqual(response.status_code, 202)
        return response.json()

    async def test_relationship_lifecycle_is_persisted_and_scoped(self) -> None:
        started = await self._start()
        async with SessionLocal() as session:
            job = await session.get(JobRun, uuid.UUID(started["job_id"]))
            expected = job.idempotency_key.split(":retry:", 1)[0].rsplit(":", 1)[1]
            self.assertEqual(await resolution_state_hash(session, self.version_id), expected)
            self.assertEqual(len(await chunk_inputs(session, self.version_id)), 2)

        async def extract(inputs, *_args, **_kwargs):
            ended = "divorced" in inputs.evidence[0].text
            return self._result(
                inputs, ended=ended, event_participants=not ended,
            )

        with patch(
            "app.queue.tasks.structured_memory.extract_structured_memory",
            side_effect=extract,
        ):
            await run_structured_memory_job(uuid.UUID(started["job_id"]))

        # Database timestamps can tie or disagree with narrative order; the API
        # must use the server-owned evidence position instead.
        async with SessionLocal() as session:
            rows = list(await session.scalars(select(Event).where(
                Event.job_id == uuid.UUID(started["job_id"])
            )))
            by_type = {item.event_type: item for item in rows}
            now = datetime.now(timezone.utc)
            by_type["relationship_started"].created_at = now + timedelta(days=1)
            by_type["relationship_ended"].created_at = now
            await session.commit()

        first_status = (await self.client.get(
            f"/api/projects/{self.project_id}/structured-memory/status"
        )).json()
        self.assertEqual(first_status["job"]["status"], "completed", first_status)
        relationships = (await self.client.get(
            f"/api/projects/{self.project_id}/relationships"
        )).json()
        self.assertEqual(len(relationships), 1, (started, relationships))
        self.assertEqual(relationships[0]["status"], "ended")
        self.assertIsNotNone(relationships[0]["start_event_id"])
        self.assertIsNotNone(relationships[0]["end_event_id"])
        self.assertEqual(len(relationships[0]["evidence"]), 2)
        events = (await self.client.get(
            f"/api/projects/{self.project_id}/events"
        )).json()
        self.assertEqual([item["type"] for item in events], [
            "relationship_started", "relationship_ended"
        ])
        self.assertTrue(all(
            item["participants"] == ["Ilya", "Mara"] for item in events
        ), events)
        self.assertEqual((await self.client.get(
            f"/api/projects/{self.other_project_id}/relationships"
        )).json(), [])

        status_payload = (await self.client.get(
            f"/api/projects/{self.project_id}/structured-memory/status"
        )).json()
        self.assertEqual(status_payload["job"]["status"], "completed", status_payload)
        self.assertEqual(status_payload["completed_chunks"], 2)
        with patch(
            "app.api.structured_memory.build_structured_memory.kiq", new=AsyncMock()
        ) as queued:
            repeated = await self.client.post(
                f"/api/projects/{self.project_id}/structured-memory/run",
                json={"manuscript_version_id": str(self.version_id)},
            )
        self.assertEqual(repeated.json()["job_id"], started["job_id"])
        queued.assert_not_awaited()

        with patch(
            "app.api.structured_memory.build_structured_memory.kiq", new=AsyncMock()
        ) as queued:
            rebuilt = await self.client.post(
                f"/api/projects/{self.project_id}/structured-memory/run",
                json={
                    "manuscript_version_id": str(self.version_id),
                    "rebuild": True,
                },
            )
        self.assertNotEqual(rebuilt.json()["job_id"], started["job_id"])
        queued.assert_awaited_once()

    async def test_failed_chunk_is_visible_and_omitted(self) -> None:
        started = await self._start()
        calls = 0

        async def extract(inputs, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise StructuredMemoryError("private invalid output")
            return self._result(inputs, fact=True)

        with patch(
            "app.queue.tasks.structured_memory.extract_structured_memory",
            side_effect=extract,
        ):
            await run_structured_memory_job(uuid.UUID(started["job_id"]))

        status_payload = (await self.client.get(
            f"/api/projects/{self.project_id}/structured-memory/status"
        )).json()
        self.assertEqual(status_payload["job"]["status"], "completed")
        self.assertEqual(status_payload["job"]["error_code"], "STRUCTURED_MEMORY_CHUNK_ERRORS")
        self.assertEqual((status_payload["completed_chunks"], status_payload["failed_chunks"]), (1, 1))
        facts = (await self.client.get(
            f"/api/projects/{self.project_id}/facts"
        )).json()
        self.assertEqual(len(facts), 1)
        self.assertNotIn("private invalid output", str(status_payload))

    async def test_stale_memory_is_hidden_when_resolution_inputs_change(self) -> None:
        async with SessionLocal() as session:
            session.add(EntityAlias(
                entity_id=self.mara_id,
                alias="Captain Mara",
                normalized_alias="captain mara",
            ))
            await session.commit()
            before = await resolution_state_hash(session, self.version_id)

        started = await self._start()

        async def extract(inputs, *_args, **_kwargs):
            return self._result(inputs, fact=True)

        with patch(
            "app.queue.tasks.structured_memory.extract_structured_memory",
            side_effect=extract,
        ):
            await run_structured_memory_job(uuid.UUID(started["job_id"]))
        self.assertEqual(len((await self.client.get(
            f"/api/projects/{self.project_id}/facts"
        )).json()), 1)

        async with SessionLocal() as session:
            alias = await session.scalar(select(EntityAlias).where(
                EntityAlias.entity_id == self.mara_id,
                EntityAlias.normalized_alias == "captain mara",
            ))
            alias.alias = "Captain  Mara"
            await session.commit()
            self.assertNotEqual(
                before, await resolution_state_hash(session, self.version_id)
            )

        status_payload = (await self.client.get(
            f"/api/projects/{self.project_id}/structured-memory/status"
        )).json()
        self.assertIsNone(status_payload["job"], status_payload)
        self.assertEqual((await self.client.get(
            f"/api/projects/{self.project_id}/facts"
        )).json(), [])

    async def test_lower_coverage_rebuild_keeps_best_result_and_retry_queues(self) -> None:
        first = await self._start()

        async def complete(inputs, *_args, **_kwargs):
            return self._result(inputs, fact=True)

        with patch(
            "app.queue.tasks.structured_memory.extract_structured_memory",
            side_effect=complete,
        ):
            await run_structured_memory_job(uuid.UUID(first["job_id"]))
        original_facts = (await self.client.get(
            f"/api/projects/{self.project_id}/facts"
        )).json()

        with patch(
            "app.api.structured_memory.build_structured_memory.kiq", new=AsyncMock()
        ):
            response = await self.client.post(
                f"/api/projects/{self.project_id}/structured-memory/run",
                json={
                    "manuscript_version_id": str(self.version_id),
                    "rebuild": True,
                },
            )
        rebuilt = response.json()
        calls = 0

        async def lower_coverage(inputs, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise StructuredMemoryError("private invalid output")
            return self._result(inputs, fact=True)

        with patch(
            "app.queue.tasks.structured_memory.extract_structured_memory",
            side_effect=lower_coverage,
        ):
            await run_structured_memory_job(uuid.UUID(rebuilt["job_id"]))

        status_payload = (await self.client.get(
            f"/api/projects/{self.project_id}/structured-memory/status"
        )).json()
        self.assertEqual(status_payload["job"]["status"], "failed")
        self.assertEqual(
            status_payload["job"]["error_code"],
            "STRUCTURED_MEMORY_NOT_IMPROVED",
        )
        self.assertEqual((await self.client.get(
            f"/api/projects/{self.project_id}/facts"
        )).json(), original_facts)

        with patch(
            "app.api.structured_memory.build_structured_memory.kiq", new=AsyncMock()
        ) as queued:
            retry = await self.client.post(
                f"/api/projects/{self.project_id}/structured-memory/run",
                json={"manuscript_version_id": str(self.version_id)},
            )
        self.assertEqual(retry.status_code, 202)
        self.assertNotIn(
            retry.json()["job_id"], {first["job_id"], rebuilt["job_id"]}
        )
        queued.assert_awaited_once()

    async def test_retry_cannot_swap_one_successful_chunk_for_another(self) -> None:
        first = await self._start()
        calls = 0

        async def first_chunk_only(inputs, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise StructuredMemoryError("private invalid output")
            return self._result(inputs, fact=True)

        with patch(
            "app.queue.tasks.structured_memory.extract_structured_memory",
            side_effect=first_chunk_only,
        ):
            await run_structured_memory_job(uuid.UUID(first["job_id"]))
        original_facts = (await self.client.get(
            f"/api/projects/{self.project_id}/facts"
        )).json()

        second = await self._start()
        calls = 0

        async def second_chunk_only(inputs, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise StructuredMemoryError("private invalid output")
            return self._result(inputs, fact=True, ended=True)

        with patch(
            "app.queue.tasks.structured_memory.extract_structured_memory",
            side_effect=second_chunk_only,
        ):
            await run_structured_memory_job(uuid.UUID(second["job_id"]))

        status_payload = (await self.client.get(
            f"/api/projects/{self.project_id}/structured-memory/status"
        )).json()
        self.assertEqual(
            status_payload["job"]["error_code"],
            "STRUCTURED_MEMORY_NOT_IMPROVED",
        )
        self.assertEqual((await self.client.get(
            f"/api/projects/{self.project_id}/facts"
        )).json(), original_facts)


if __name__ == "__main__":
    unittest.main()
