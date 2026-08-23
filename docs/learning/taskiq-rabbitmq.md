# Taskiq + RabbitMQ

## Mental model

```text
RabbitMQ  = durable task delivery
Taskiq    = producer/worker execution framework
PostgreSQL = authoritative job state and progress
```

StoryGuard assumes at-least-once delivery: a worker may execute a task again after
a failure or lost acknowledgement. Task code must therefore make repeated delivery
safe instead of assuming exactly-once execution.

## StoryGuard implementation

- `backend/app/queue/broker.py` connects Taskiq to RabbitMQ and configures two
  transient retries after the initial attempt: 5 seconds, then 30 seconds, with
  jitter.
- `backend/app/db/models/job_run.py` stores job type, project/version scope,
  status, stage, progress, idempotency key, attempts, safe failure details, and
  timestamps.
- `backend/app/queue/tasks/smoke.py` provides the current infrastructure task. It
  locks the job row, records execution, completes it, and returns immediately if
  that job has already completed.
- `backend/migrations/versions/20260822_03_create_job_runs.py` creates the durable
  job-state table and its constraints.
- `compose.yaml` runs Taskiq in a separate worker process with acknowledgement
  after execution and starts it only after RabbitMQ, PostgreSQL, and the migrated
  backend are ready.

Execution flow:

```text
create job_runs(status=queued)
-> task.kiq(job_id)
-> RabbitMQ retains the message
-> Taskiq worker receives it
-> lock job row
-> status=running, attempts += 1
-> perform work
-> status=completed, progress=1/1
-> acknowledge the RabbitMQ message
```

The queue-smoke task is intentionally small. It proves the process boundary and
state transitions without pretending that manuscript parsing already exists.

## Why this design

- FastAPI should return quickly instead of processing a complete manuscript in an
  HTTP request.
- RabbitMQ transports work but is not a queryable business-history database.
- PostgreSQL lets the UI and operators read durable status, progress, attempts,
  and safe errors after messages have been acknowledged.
- `idempotency_key` prevents duplicate logical job records. Task-level guards and
  version-scoped database constraints protect the effects of repeated execution.
- A Redis result backend, separate worker pools, upload API, and fake ingestion
  stages were not added because the current lesson does not need them.

## Failure and retry behavior

The worker acknowledges messages after execution. If the worker is unavailable,
RabbitMQ retains the queued message; the verified job ran after the worker was
started again.

Only connectivity-style failures (`ConnectionError`, `TimeoutError`, and
SQLAlchemy `OperationalError`) use the configured retry policy. Permanent errors
such as a missing job are not retried. Stored error text is safe for UI display;
internal exception details remain in logs.

The current duplicate-delivery test repeats an already completed job and verifies
that `attempts` remains `1`. Real ingestion will additionally need version-scoped
unique constraints and a cleanup/full-rebuild boundary so a retry cannot duplicate
chapters, chunks, entities, facts, or events. Resuming from a detailed checkpoint
is deferred until measurements justify its extra state and failure modes.

## Verification and observations

- Full backend unit/integration suite: 10 passed, 0 failed.
- Alembic revision `20260822_03` is at head.
- A real producer-to-RabbitMQ-to-worker smoke job completed with
  `status=completed`, `attempts=1`, and `stage=queue_smoke`.
- With the worker stopped, a job remained `queued` with zero attempts; after the
  worker started, it completed with one attempt.
- Repeating a completed job was a no-op because the status guard executes before
  `attempts += 1`.

This lesson has no LLM calls, LangSmith traces, AI evaluations, or model cost.
Queue latency and throughput were not benchmarked; a single local worker remains
appropriate until measurements show otherwise.

## Security and reliability

- Job rows carry project and optional manuscript-version foreign keys.
- Database constraints restrict status values, non-negative attempts, and unique
  idempotency keys.
- The worker receives server-issued IDs rather than manuscript content as task
  authority.
- Stack traces are not stored in UI-facing error fields.
- Project/version authorization belongs at the API boundary when jobs become
  user-triggered; the smoke task has no public endpoint.

## Interview questions

1. Why is RabbitMQ not the source of truth for job status?
2. What does at-least-once delivery require from task side effects?
3. Why should acknowledgement happen after safe task execution?
4. How do transient and permanent failures differ under a retry policy?
5. Why is full version-scoped rebuild a reasonable v1 retry strategy?
