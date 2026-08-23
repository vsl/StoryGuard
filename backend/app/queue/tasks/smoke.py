import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models.job_run import JobRun
from app.db.session import SessionLocal
from app.queue.broker import broker


async def run_queue_smoke(job_id: uuid.UUID) -> None:
    async with SessionLocal() as session, session.begin():
        job = await session.scalar(
            select(JobRun).where(JobRun.id == job_id).with_for_update()
        )
        if job is None:
            raise LookupError("Job not found")
        if job.status == "completed":
            return
        job.status = "running"
        job.stage = "queue_smoke"
        job.attempts += 1
        job.started_at = job.started_at or datetime.now(timezone.utc)
        job.completed_at = None
        job.error_code = job.error_message_safe = None

    try:
        async with SessionLocal() as session, session.begin():
            job = await session.get(JobRun, job_id, with_for_update=True)
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            job.completed_units = job.total_units = 1
    except Exception:
        async with SessionLocal() as session, session.begin():
            job = await session.get(JobRun, job_id, with_for_update=True)
            if job is not None and job.status != "completed":
                job.status = "failed"
                job.error_code = "QUEUE_SMOKE_FAILED"
                job.error_message_safe = "The background task could not be completed."
                job.completed_at = datetime.now(timezone.utc)
        raise


@broker.task(retry_on_error=True)
async def queue_smoke(job_id: str) -> None:
    await run_queue_smoke(uuid.UUID(job_id))
