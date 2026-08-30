import asyncio
import os
import unittest
import uuid
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

    async def _upload(self, name: str = "story.txt") -> dict:
        with patch(
            "app.api.ingestion.parse_and_ingest_manuscript.kiq", new=AsyncMock()
        ):
            response = await self.client.post(
                f"/api/projects/{self.project_id}/manuscripts",
                files={"file": (name, b"Chapter 1\nAlice waited.", "text/plain")},
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
        self.assertNotIn("object_key", job)

    async def test_queue_failure_is_safe_and_does_not_replace_current(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
