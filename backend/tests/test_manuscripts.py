import asyncio
import hashlib
import io
import os
import unittest
import uuid
from unittest.mock import AsyncMock, Mock, patch

from app.db.models.project import Project
from app.manuscripts import (
    create_manuscript_version,
    inspect_upload,
    minio_client,
    object_key,
)


class ManuscriptTest(unittest.IsolatedAsyncioTestCase):
    def test_validates_upload_and_generates_server_key(self) -> None:
        project_id, version_id = uuid.uuid4(), uuid.uuid4()
        data = b"# Story"
        name, size, content_hash = inspect_upload(
            "../../draft.md", "text/markdown", io.BytesIO(data)
        )

        self.assertEqual((name, size), ("draft.md", len(data)))
        self.assertEqual(content_hash, hashlib.sha256(data).hexdigest())
        self.assertEqual(
            object_key(project_id, version_id, ".md"),
            f"projects/{project_id}/manuscripts/{version_id}/original.md",
        )

        with self.assertRaisesRegex(ValueError, "Unsupported"):
            inspect_upload("story.exe", "application/octet-stream", io.BytesIO(b"x"))
        with patch.dict(os.environ, {"MANUSCRIPT_MAX_BYTES": "1"}), self.assertRaisesRegex(
            ValueError, "size limit"
        ):
            inspect_upload("story.txt", "text/plain", io.BytesIO(b"xx"))

    async def test_storage_and_database_failures_are_compensated(self) -> None:
        project_id = uuid.uuid4()
        session = AsyncMock()
        session.add = Mock()
        session.scalar.side_effect = [Project(id=project_id, title="Story"), 0]

        with patch("app.manuscripts._store", side_effect=RuntimeError("storage")):
            with self.assertRaisesRegex(RuntimeError, "storage"):
                await create_manuscript_version(
                    session, project_id, "story.txt", "text/plain", io.BytesIO(b"text")
                )
        session.add.assert_not_called()
        session.rollback.assert_awaited_once()

        session.reset_mock()
        session.scalar.side_effect = [Project(id=project_id, title="Story"), 0]
        session.commit.side_effect = RuntimeError("database")
        with (
            patch("app.manuscripts._store"),
            patch("app.manuscripts._remove") as remove,
            self.assertRaisesRegex(RuntimeError, "database"),
        ):
            await create_manuscript_version(
                session, project_id, "story.txt", "text/plain", io.BytesIO(b"text")
            )
        remove.assert_called_once()
        session.rollback.assert_awaited_once()


RUN_DATABASE_TESTS = os.environ.get("RUN_DATABASE_TESTS") == "1"

if RUN_DATABASE_TESTS:
    from sqlalchemy import select

    from app.db.models.manuscript_version import ManuscriptVersion
    from app.db.session import SessionLocal, engine


@unittest.skipUnless(RUN_DATABASE_TESTS, "set RUN_DATABASE_TESTS=1")
class ManuscriptIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.project_id = uuid.uuid4()
        self.object_keys: list[str] = []
        async with SessionLocal() as session:
            session.add(Project(id=self.project_id, title="The Last Signal"))
            await session.commit()

    async def asyncTearDown(self) -> None:
        client = minio_client()
        bucket = os.environ["MINIO_BUCKET"]
        for key in self.object_keys:
            await asyncio.to_thread(client.remove_object, bucket, key)
        async with SessionLocal() as session:
            project = await session.get(Project, self.project_id)
            if project:
                await session.delete(project)
                await session.commit()
        await engine.dispose()

    async def test_original_and_metadata_are_stored_without_publication(self) -> None:
        data = b"Daniel is 32."
        async with SessionLocal() as session:
            version = await create_manuscript_version(
                session,
                self.project_id,
                "draft.txt",
                "text/plain",
                io.BytesIO(data),
            )
            self.object_keys.append(version.object_key)

        response = await asyncio.to_thread(
            minio_client().get_object, os.environ["MINIO_BUCKET"], version.object_key
        )
        try:
            stored = await asyncio.to_thread(response.read)
        finally:
            response.close()
            response.release_conn()

        async with SessionLocal() as session:
            project = await session.get(Project, self.project_id)
            persisted = await session.scalar(
                select(ManuscriptVersion).where(ManuscriptVersion.id == version.id)
            )
        self.assertEqual(stored, data)
        self.assertEqual(persisted.status, "uploaded")
        self.assertEqual(persisted.content_hash, hashlib.sha256(data).hexdigest())
        self.assertIsNone(project.current_manuscript_version_id)


if __name__ == "__main__":
    unittest.main()
