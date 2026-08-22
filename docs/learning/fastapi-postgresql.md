# FastAPI + PostgreSQL

## Mental model

```text
HTTP request
→ FastAPI + Pydantic validation
→ request-scoped AsyncSession
→ SQLAlchemy transaction
→ PostgreSQL commit
→ session closes
```

PostgreSQL preserves committed project data independently of the FastAPI process.
An `AsyncSession` is temporary, mutable transaction state for one request. Async
database I/O lets the event loop serve other work while PostgreSQL is responding;
it does not make a session safe to share between requests.

## StoryGuard implementation

- `backend/app/main.py` registers project routes, checks PostgreSQL readiness through
  the shared SQLAlchemy engine, and disposes the connection pool on shutdown.
- `backend/app/db/session.py` creates the async engine and yields one `AsyncSession`
  per request. Exceptions roll back that request's transaction.
- `backend/app/api/projects.py` implements create, list, get, patch, and delete.
- `backend/app/schemas/projects.py` validates HTTP input and serializes ORM output.
- `backend/app/db/models/project.py` maps the Python `Project` class to `projects`.
- `backend/migrations/versions/20260822_01_create_projects.py` creates the schema;
  application startup never calls `metadata.create_all()`.

Create request flow:

```text
POST /api/projects
→ ProjectCreate
→ create_project()
→ get_session()
→ INSERT projects
→ COMMIT
→ refresh server-generated timestamps
→ ProjectRead
```

## Why this design

- PostgreSQL is StoryGuard's authoritative structured store.
- SQLAlchemy 2.x provides explicit queries, transactions, mapping, and pooling.
- Alembic makes schema changes ordered, reviewable, and repeatable.
- Request-scoped sessions isolate concurrent transactions.
- Routes use SQLAlchemy directly for now; repository/service layers would add no
  useful boundary until domain logic is reused or becomes complex.

Alternatives not chosen:

- Raw `asyncpg` for CRUD would duplicate mapping and migration concerns.
- A global `AsyncSession` would mix concurrent transaction state.
- `metadata.create_all()` at startup would not provide migration history.
- SQLite would not exercise the PostgreSQL behavior used by StoryGuard.

## Failure case

If one session flushes an insert and later fails, rollback removes that provisional
row. A separate session may commit another project successfully; the rollback does
not affect it. If PostgreSQL is unavailable, `/health/ready` reports `503` and no
partial project transaction is committed.

## Verification and observations

- Unit and PostgreSQL integration tests: 5 passed.
- CRUD path: create, list, get, patch, delete, then missing-project `404`.
- Transaction check: one flushed project rolled back while another session's project
  committed; only the committed project remained.
- Alembic drift check: no new upgrade operations detected.
- Docker smoke: liveness `alive`, readiness `ready`, CRUD round trip succeeded.
- Developer checkpoint: a committed project survived a FastAPI restart because it
  lived in PostgreSQL; the original request session had already closed.

This lesson has no LLM calls, LangSmith traces, AI evaluation metrics, or API-model
cost. Async I/O improves concurrency while waiting on the database, but no latency
claim is made without a benchmark. Pool size and query tuning are deferred until
measurements show a need.

## Security and reliability

- Database credentials remain in `DATABASE_URL`, outside browser responses.
- Pydantic rejects invalid request bodies before SQL execution.
- SQLAlchemy uses bound parameters rather than interpolated user SQL.
- Rollback prevents failed requests from persisting partial changes.
- API responses do not expose database connection strings or stack traces.

## Interview questions

1. Why should an `AsyncSession` be scoped to one request or async task?
2. What is the difference between `flush()`, `commit()`, and `rollback()`?
3. Why use Alembic instead of creating ORM tables during application startup?
4. What survives a FastAPI restart, and why?
5. How does asynchronous database I/O differ from transaction isolation?
