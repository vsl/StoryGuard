import os
import unittest
import uuid
from unittest.mock import Mock, patch

RUN_DATABASE_TESTS = os.environ.get("RUN_DATABASE_TESTS") == "1"

if RUN_DATABASE_TESTS:
    from sqlalchemy import select

    from app.db.models.job_run import JobRun
    from app.db.models.project import Project
    from app.db.session import SessionLocal, engine
    from app.queue.broker import StoryGuardRetryMiddleware, broker
    from app.queue.tasks.smoke import run_queue_smoke


@unittest.skipUnless(RUN_DATABASE_TESTS, "set RUN_DATABASE_TESTS=1")
class QueueIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.project_id = uuid.uuid4()
        self.job_id = uuid.uuid4()
        async with SessionLocal() as session:
            session.add(Project(id=self.project_id, title="Queue smoke"))
            await session.commit()
            session.add(
                JobRun(
                    id=self.job_id,
                    job_type="queue_smoke",
                    project_id=self.project_id,
                    idempotency_key=f"queue_smoke:{self.job_id}",
                )
            )
            await session.commit()

    async def asyncTearDown(self) -> None:
        async with SessionLocal() as session:
            project = await session.get(Project, self.project_id)
            if project:
                await session.delete(project)
                await session.commit()
        await engine.dispose()

    async def test_duplicate_delivery_is_a_no_op(self) -> None:
        await run_queue_smoke(self.job_id)
        await run_queue_smoke(self.job_id)

        async with SessionLocal() as session:
            job = await session.scalar(select(JobRun).where(JobRun.id == self.job_id))
        self.assertEqual((job.status, job.attempts), ("completed", 1))
        self.assertEqual((job.completed_units, job.total_units), (1, 1))

    def test_retry_baseline_is_two_retries_at_5_and_30_seconds(self) -> None:
        middleware = StoryGuardRetryMiddleware(default_retry_count=3)
        message = Mock(labels={})
        with patch("app.queue.broker.random.random", return_value=0.25):
            self.assertEqual(middleware.make_delay(message, 1), 5.25)
            self.assertEqual(middleware.make_delay(message, 2), 30.25)
        self.assertEqual(middleware.default_retry_count, 3)

        configured = broker.middlewares[0]
        self.assertNotIn(LookupError, configured.types_of_exceptions)


if __name__ == "__main__":
    unittest.main()
