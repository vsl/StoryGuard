import asyncio
import os
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def fake_embeddings(texts: list[str]) -> list[list[float]]:
    return [[1.0, *([0.0] * 767)] for _ in texts]


class IdentityReranker:
    def rerank(self, _query, candidates, top_k):
        return candidates[:top_k]


RUN_DATABASE_TESTS = os.environ.get("RUN_DATABASE_TESTS") == "1"

if RUN_DATABASE_TESTS:
    import httpx
    from sqlalchemy import select

    from app.ai.retrieval import replace_version_chunks
    from app.db.models.manuscript_version import ManuscriptVersion
    from app.db.models.job_run import JobRun
    from app.db.models.entity_mention import EntityMention
    from app.db.models.project import Project
    from app.db.session import SessionLocal, engine
    from app.main import app
    from app.manuscripts import minio_client
    from app.queue.tasks.ingestion import run_parse_and_ingest


@unittest.skipUnless(RUN_DATABASE_TESTS, "set RUN_DATABASE_TESTS=1")
class ApplicationApiIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.project_id = uuid.uuid4()
        self.other_project_id = uuid.uuid4()
        self.object_keys: list[str] = []
        self.version_ids: list[uuid.UUID] = []
        async with SessionLocal() as session:
            session.add_all(
                [
                    Project(id=self.project_id, title="API story"),
                    Project(id=self.other_project_id, title="Other story"),
                ]
            )
            await session.commit()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )

    async def asyncTearDown(self) -> None:
        client = minio_client()
        bucket = os.environ["MINIO_BUCKET"]
        for key in self.object_keys:
            await asyncio.to_thread(client.remove_object, bucket, key)
        for version_id in self.version_ids:
            await replace_version_chunks(str(self.project_id), str(version_id), [])
        async with SessionLocal() as session:
            for project_id in (self.project_id, self.other_project_id):
                project = await session.get(Project, project_id)
                if project:
                    await session.delete(project)
            await session.commit()
        await self.client.aclose()
        await engine.dispose()

    async def _upload(
        self, name: str = "story.txt", extraction_model: str | None = None,
        text: bytes = b"Chapter 1\nAlice waited.",
    ) -> dict:
        with patch(
            "app.api.ingestion.parse_and_ingest_manuscript.kiq", new=AsyncMock()
        ):
            response = await self.client.post(
                f"/api/projects/{self.project_id}/manuscripts",
                files={"file": (name, text, "text/plain")},
                data={"extraction_model": extraction_model} if extraction_model else {},
            )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        version_id = uuid.UUID(payload["manuscript_version_id"])
        self.version_ids.append(version_id)
        async with SessionLocal() as session:
            version = await session.get(ManuscriptVersion, version_id)
            self.object_keys.append(version.object_key)
        return payload

    async def test_real_contract_is_scoped_and_publishes_only_after_success(self) -> None:
        upload = await self._upload()
        self.assertEqual(upload["extraction_model"], "gemma4-e4b")
        version_id = upload["manuscript_version_id"]

        versions = await self.client.get(
            f"/api/projects/{self.project_id}/manuscripts"
        )
        self.assertEqual(versions.json()[0]["status"], "uploaded")
        cross_project = await self.client.get(
            f"/api/projects/{self.other_project_id}/manuscripts/{version_id}"
        )
        self.assertEqual(cross_project.status_code, 404)
        self.assertEqual(
            (await self.client.get(f"/api/projects/{self.project_id}/chapters")).json(),
            [],
        )

        with patch(
            "app.queue.tasks.ingestion.embed_documents",
            side_effect=fake_embeddings,
        ), patch(
            "app.queue.tasks.ingestion.extract_version_entities",
            new=AsyncMock(return_value=1),
        ):
            await run_parse_and_ingest(uuid.UUID(upload["job_id"]))

        project = (
            await self.client.get(f"/api/projects/{self.project_id}")
        ).json()
        self.assertEqual(
            (project["current_manuscript_version"], project["chapter_count"]),
            ("v1", 1),
        )
        chapters = (
            await self.client.get(f"/api/projects/{self.project_id}/chapters")
        ).json()
        self.assertEqual(chapters[0]["number"], 1)
        chapter_id = chapters[0]["id"]
        detail = await self.client.get(
            f"/api/projects/{self.project_id}/chapters/{chapter_id}"
        )
        self.assertIn("Alice waited", detail.json()["text"])
        cross_project = await self.client.get(
            f"/api/projects/{self.other_project_id}/chapters/{chapter_id}"
        )
        self.assertEqual(cross_project.status_code, 404)

        with (
            patch(
                "app.ai.retrieval.embed_query",
                return_value=fake_embeddings([""])[0],
            ),
            patch("app.ai.reranking.get_reranker", return_value=IdentityReranker()),
        ):
            hybrid = await self.client.get(
                f"/api/projects/{self.project_id}/search",
                params={"q": "Alice", "rerank": "false"},
            )
            reranked = await self.client.get(
                f"/api/projects/{self.project_id}/search",
                params={"q": "Alice", "rerank": "true"},
            )
        self.assertEqual(hybrid.status_code, 200)
        self.assertEqual(reranked.status_code, 200)
        self.assertEqual(len(hybrid.json()["manuscript_matches"]), 1)
        self.assertEqual(len(reranked.json()["manuscript_matches"]), 1)
        self.assertIn(
            "Alice waited", reranked.json()["manuscript_matches"][0]["text"]
        )
        self.assertEqual(
            (
                await self.client.get(
                    f"/api/projects/{self.other_project_id}/search",
                    params={"q": "Alice"},
                )
            ).json()["manuscript_matches"],
            [],
        )

        with patch(
            "app.api.projects.retrieve_hybrid",
            new=AsyncMock(side_effect=RuntimeError("internal secret")),
        ):
            unavailable = await self.client.get(
                f"/api/projects/{self.project_id}/search",
                params={"q": "Alice", "rerank": "false"},
            )
        self.assertEqual(unavailable.status_code, 503)
        self.assertEqual(unavailable.json()["error"]["code"], "RETRIEVAL_UNAVAILABLE")
        self.assertNotIn("internal secret", unavailable.text)

        job = (await self.client.get(f"/api/jobs/{upload['job_id']}")).json()
        self.assertEqual((job["status"], job["completed"], job["total"]), ("completed", 1, 1))
        self.assertEqual(set(job["stage_durations_ms"]), {"parsing", "embedding", "indexing", "entity_extraction"})
        self.assertIsNone(job["current_stage_elapsed_ms"])
        self.assertIsNotNone(job["completed_at"])
        self.assertNotIn("object_key", job)

    async def test_extractor_catalog_selection_and_validation(self) -> None:
        catalog = (await self.client.get("/api/extraction-models")).json()
        self.assertEqual(catalog["default"], "gemma4-e4b")
        self.assertEqual(
            {item["id"] for item in catalog["items"]},
            {"gemma4-e4b", "gliner2.5-base-v1", "qwen3.5-9b"},
        )
        for item in catalog["items"]:
            upload = await self._upload(extraction_model=item["id"])
            self.assertEqual(upload["extraction_model"], item["id"])
            detail = await self.client.get(
                f"/api/projects/{self.project_id}/manuscripts/{upload['manuscript_version_id']}"
            )
            self.assertEqual(detail.json()["extraction_model"], item["id"])
            self.assertNotIn("object_key", detail.json())
        with patch("app.api.ingestion.create_manuscript_version", new=AsyncMock()) as create:
            for invalid in ("qwen3.5-4b", "http://attacker/model", "unknown"):
                response = await self.client.post(
                    f"/api/projects/{self.project_id}/manuscripts",
                    files={"file": ("story.txt", b"Text", "text/plain")},
                    data={"extraction_model": invalid},
                )
                self.assertEqual(response.status_code, 422)
            create.assert_not_awaited()

    async def test_queue_failure_is_safe_and_does_not_replace_current(self) -> None:
        older = await self._upload()
        with patch(
            "app.api.ingestion.parse_and_ingest_manuscript.kiq",
            new=AsyncMock(side_effect=RuntimeError("amqp://secret")),
        ):
            response = await self.client.post(
                f"/api/projects/{self.project_id}/manuscripts",
                files={"file": ("failed.txt", b"Chapter 1\nText", "text/plain")},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "QUEUE_UNAVAILABLE")
        self.assertNotIn("secret", response.text)

        async with SessionLocal() as session:
            version = await session.scalar(
                select(ManuscriptVersion)
                .where(ManuscriptVersion.project_id == self.project_id)
                .order_by(ManuscriptVersion.version_number.desc())
            )
            self.object_keys.append(version.object_key)
            self.version_ids.append(version.id)
            project = await session.get(Project, self.project_id)
        self.assertEqual(version.status, "failed")
        self.assertIsNone(project.current_manuscript_version_id)
        old_job = (await self.client.get(f"/api/jobs/{older['job_id']}")).json()
        self.assertEqual(old_job["status"], "queued")

    async def test_cancel_is_scoped_idempotent_and_redelivery_does_no_work(self) -> None:
        upload = await self._upload()
        version_id = upload["manuscript_version_id"]
        other = await self.client.post(
            f"/api/projects/{self.other_project_id}/manuscripts/{version_id}/cancel"
        )
        self.assertEqual(other.status_code, 404)
        for _ in range(2):
            response = await self.client.post(
                f"/api/projects/{self.project_id}/manuscripts/{version_id}/cancel"
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "cancelled")
        with patch("app.queue.tasks.ingestion._download") as download:
            await run_parse_and_ingest(uuid.UUID(upload["job_id"]))
            download.assert_not_called()
        async with SessionLocal() as session:
            job = await session.get(JobRun, uuid.UUID(upload["job_id"]))
            self.assertEqual((job.status, job.attempts), ("cancelled", 0))
            self.assertIsNotNone(job.completed_at)
            self.assertEqual(job.error_code, "USER_CANCELLED")

    async def test_cancel_during_extraction_stops_next_chunk_and_preserves_current(self) -> None:
        ready = await self._upload()
        with (
            patch("app.queue.tasks.ingestion.embed_documents", side_effect=fake_embeddings),
            patch("app.queue.tasks.ingestion.extract_version_entities", new=AsyncMock(return_value=1)),
        ):
            await run_parse_and_ingest(uuid.UUID(ready["job_id"]))
        completed_cancel = await self.client.post(
            f"/api/projects/{self.project_id}/manuscripts/{ready['manuscript_version_id']}/cancel"
        )
        self.assertEqual(completed_cancel.status_code, 409)
        upload = await self._upload(text=b"Chapter 1\nAlice waited.\n\n***\n\nBob arrived.")
        started, release = asyncio.Event(), asyncio.Event()

        async def extract(*args, **kwargs):
            started.set()
            await release.wait()
            return SimpleNamespace(mentions=[])

        with (
            patch("app.queue.tasks.ingestion.embed_documents", side_effect=fake_embeddings),
            patch("app.entity_mentions.extract_entities", side_effect=extract) as model,
        ):
            task = asyncio.create_task(run_parse_and_ingest(uuid.UUID(upload["job_id"])))
            try:
                await asyncio.wait_for(started.wait(), 15)
                response = await self.client.post(
                    f"/api/projects/{self.project_id}/manuscripts/{upload['manuscript_version_id']}/cancel"
                )
                self.assertEqual(response.json()["status"], "cancelled")
            finally:
                release.set()
                await asyncio.wait_for(task, 15)
            self.assertEqual(model.call_count, 1)
        async with SessionLocal() as session:
            job = await session.get(JobRun, uuid.UUID(upload["job_id"]))
            project = await session.get(Project, self.project_id)
            mentions = list(await session.scalars(select(EntityMention).where(
                EntityMention.manuscript_version_id == uuid.UUID(upload["manuscript_version_id"])
            )))
        self.assertEqual(job.status, "cancelled")
        self.assertIn("entity_extraction", job.stage_durations_ms)
        self.assertEqual(mentions, [])
        self.assertEqual(str(project.current_manuscript_version_id), ready["manuscript_version_id"])

    async def test_new_upload_cancels_running_job_even_if_its_model_call_fails(self) -> None:
        older = await self._upload()
        async with SessionLocal() as session:
            other_job = JobRun(
                job_type="parse_and_ingest_manuscript", project_id=self.other_project_id,
                idempotency_key=f"other:{uuid.uuid4()}", status="running",
            )
            session.add(other_job)
            await session.commit()
        started, release = asyncio.Event(), asyncio.Event()

        async def extract(*args, **kwargs):
            started.set()
            await release.wait()
            raise TimeoutError("private provider error")

        with (
            patch("app.queue.tasks.ingestion.embed_documents", side_effect=fake_embeddings),
            patch("app.queue.tasks.ingestion.extract_version_entities", side_effect=extract),
        ):
            task = asyncio.create_task(run_parse_and_ingest(uuid.UUID(older["job_id"])))
            try:
                await asyncio.wait_for(started.wait(), 15)
                newer = await self._upload()
            finally:
                release.set()
                await asyncio.wait_for(task, 15)
        async with SessionLocal() as session:
            old = await session.get(JobRun, uuid.UUID(older["job_id"]))
            new = await session.get(JobRun, uuid.UUID(newer["job_id"]))
            other = await session.get(JobRun, other_job.id)
            self.assertEqual((old.status, old.error_code), ("cancelled", "SUPERSEDED"))
            self.assertEqual((new.status, other.status), ("queued", "running"))
        with patch("app.queue.tasks.ingestion._download") as download:
            await run_parse_and_ingest(uuid.UUID(older["job_id"]))
            download.assert_not_called()

    async def test_late_completion_and_old_worker_redelivery_cannot_replace_newer(self) -> None:
        older = await self._upload()
        started, release = asyncio.Event(), asyncio.Event()

        async def extract(*args, **kwargs):
            started.set()
            await release.wait()
            return 0

        with (
            patch("app.queue.tasks.ingestion.embed_documents", side_effect=fake_embeddings),
            patch("app.queue.tasks.ingestion.extract_version_entities", side_effect=extract),
        ):
            task = asyncio.create_task(run_parse_and_ingest(uuid.UUID(older["job_id"])))
            try:
                await asyncio.wait_for(started.wait(), 15)
                newer = await self._upload()
                with patch("app.queue.tasks.ingestion.extract_version_entities", new=AsyncMock(return_value=0)):
                    await run_parse_and_ingest(uuid.UUID(newer["job_id"]))
                # Simulate a pre-upgrade worker/failed retry whose old status was never cancelled.
                async with SessionLocal() as session:
                    job = await session.get(JobRun, uuid.UUID(older["job_id"]))
                    version = await session.get(ManuscriptVersion, uuid.UUID(older["manuscript_version_id"]))
                    job.status, version.status = "running", "processing"
                    await session.commit()
            finally:
                release.set()
                await asyncio.wait_for(task, 15)
        async with SessionLocal() as session:
            project = await session.get(Project, self.project_id)
            old = await session.get(JobRun, uuid.UUID(older["job_id"]))
            self.assertEqual(str(project.current_manuscript_version_id), newer["manuscript_version_id"])
            self.assertEqual(old.status, "cancelled")
            old.status = "failed"
            await session.commit()
        with patch("app.queue.tasks.ingestion._download") as download:
            await run_parse_and_ingest(uuid.UUID(older["job_id"]))
            download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
