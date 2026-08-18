# Backend Rules

Read root `AGENTS.md` and the backend/AI spec first.

## Boundaries
- FastAPI: HTTP/application layer and interactive SSE AI requests.
- Taskiq + RabbitMQ: long-running/background batch execution.
- LangGraph: AI workflow state/routing/branching/planning/fallback/verification.
- PostgreSQL: structured source of truth.
- Elasticsearch: derived retrieval index.
- MinIO: object/file storage.
- LiteLLM: generative-model gateway/routing/fallback.
- LangSmith: AI observability/evaluation.

Do not blur these boundaries for convenience.

## Python
- Use async I/O where supported.
- Use Pydantic at API and LLM structured-output boundaries.
- Use SQLAlchemy 2.x and Alembic.
- Avoid untyped dictionaries for stable domain contracts.

## Data/versioning
- Every version-sensitive story datum is scoped to `manuscript_version_id`.
- Current-version publication is atomic.
- Retried jobs are idempotent.
- Elasticsearch is never authoritative application state.

## Testing
Add the narrowest useful unit, integration, API-contract, and failure-path tests.
