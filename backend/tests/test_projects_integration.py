import os
import unittest
import uuid

RUN_DATABASE_TESTS = os.environ.get("RUN_DATABASE_TESTS") == "1"

if RUN_DATABASE_TESTS:
    import httpx
    from sqlalchemy import select

    from app.db.models.project import Project
    from app.db.session import SessionLocal, engine
    from app.main import app


@unittest.skipUnless(RUN_DATABASE_TESTS, "set RUN_DATABASE_TESTS=1")
class ProjectApiIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )
        self.project_ids: set[str] = set()

    async def asyncTearDown(self) -> None:
        for project_id in self.project_ids:
            await self.client.delete(f"/api/projects/{project_id}")
        await self.client.aclose()
        await engine.dispose()

    async def test_project_crud(self) -> None:
        created = await self.client.post(
            "/api/projects",
            json={"title": "The Last Signal", "description": "", "language": "en"},
        )
        self.assertEqual(created.status_code, 201)
        project = created.json()
        self.project_ids.add(project["id"])

        listed = await self.client.get("/api/projects")
        self.assertEqual(listed.status_code, 200)
        self.assertIn(project["id"], {item["id"] for item in listed.json()})

        fetched = await self.client.get(f"/api/projects/{project['id']}")
        self.assertEqual(fetched.json()["title"], "The Last Signal")

        updated = await self.client.patch(
            f"/api/projects/{project['id']}", json={"title": "Last Signal"}
        )
        self.assertEqual(updated.json()["title"], "Last Signal")

        deleted = await self.client.delete(f"/api/projects/{project['id']}")
        self.assertEqual(deleted.status_code, 204)
        self.project_ids.remove(project["id"])
        missing = await self.client.get(f"/api/projects/{project['id']}")
        self.assertEqual(missing.status_code, 404)

    async def test_rollback_is_isolated_from_another_session(self) -> None:
        rolled_back_id = uuid.uuid4()
        committed_id = uuid.uuid4()
        self.project_ids.add(str(committed_id))

        async with SessionLocal() as failed, SessionLocal() as successful:
            failed.add(Project(id=rolled_back_id, title="Rollback"))
            await failed.flush()
            successful.add(Project(id=committed_id, title="Commit"))
            await successful.commit()
            await failed.rollback()

        async with SessionLocal() as session:
            result = await session.scalars(
                select(Project).where(Project.id.in_([rolled_back_id, committed_id]))
            )
            self.assertEqual({project.id for project in result}, {committed_id})


if __name__ == "__main__":
    unittest.main()
