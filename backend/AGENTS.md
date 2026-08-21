# StoryGuard Backend Instructions

Read root `AGENTS.md`, `COURSE_PROGRESS.md`, and backend spec.

The root approval gate applies here.

Boundaries:

```text
FastAPI = HTTP/application + interactive SSE
Taskiq/RabbitMQ = background execution
LangGraph = AI workflow
PostgreSQL = source of truth
Elasticsearch = derived retrieval index
MinIO = object storage
LiteLLM = model gateway/routing
LangSmith = traces/evals
```

Use:
- Pydantic
- SQLAlchemy 2.x
- Alembic
- async I/O where supported

Version-sensitive data must be scoped to manuscript version.

Test:
- deterministic logic;
- integrations;
- retries/idempotency;
- version/project isolation;
- failure behavior.

Do not implement before the course/feature approval gate is satisfied.
