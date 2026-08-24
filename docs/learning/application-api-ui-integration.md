# Application API/UI Integration Catch-up

## Mental model

Implemented domain code is not yet a product capability. A complete vertical
slice must cross every real boundary:

```text
browser
-> Next.js same-origin API proxy
-> FastAPI
-> PostgreSQL + MinIO
-> RabbitMQ / Taskiq worker
-> parser + Elasticsearch BM25 index
-> PostgreSQL job/version state
-> polling UI + chapter viewer
```

Test-only `page.route()` mocks prove that the UI handles a contract. They do not
prove that FastAPI publishes the endpoint, storage works, a worker consumes the
job, or production responses match frontend validation.

The publication invariant is:

```text
upload != current

processing succeeds -> version=ready -> atomically set project.current_version
processing fails    -> version=failed -> previous current version is unchanged
```

## StoryGuard implementation

`frontend/components/operations-screens.tsx` uploads multipart data to the
same-origin `/api` path, polls `GET /api/jobs/{job_id}`, refreshes version and
project state at a terminal job status, and marks Current by the server-issued
`current_manuscript_version_id` rather than by list position.

`backend/app/main.py` starts the Taskiq producer broker in FastAPI lifespan and
registers `backend/app/api/ingestion.py`. The router provides:

```text
POST /api/projects/{project_id}/manuscripts
GET  /api/projects/{project_id}/manuscripts
GET  /api/projects/{project_id}/manuscripts/{version_id}
GET  /api/jobs/{job_id}
GET  /api/projects/{project_id}/chapters
GET  /api/projects/{project_id}/chapters/{chapter_id}
```

The upload endpoint reuses `backend/app/manuscripts.py` for validation, hashing,
MinIO storage, and version-number allocation. It then creates a durable
`job_run` and enqueues the existing `parse_and_ingest_manuscript` Taskiq task.

`backend/app/queue/tasks/ingestion.py` downloads the immutable original, parses
chapters/scenes/chunks, replaces that version's Elasticsearch documents, and
only then commits these state changes together:

```text
job.status = completed
job.stage = bm25_indexed
version.status = ready
version.ready_at = completion time
project.current_manuscript_version_id = version.id
```

On parsing or indexing failure, the job and candidate version become failed;
the project pointer is never changed. No migration was needed because the
project, manuscript-version, job, and narrative tables already existed.

`backend/app/api/projects.py` exposes only aggregates supported by completed
lessons: current version label and current-version chapter count. Character,
issue, analysis, embedding, and continuity aggregates remain unavailable.

## Why this design

- Polling uses the existing job table and avoids a second progress system; SSE
  can be added only when real-time requirements justify it.
- Thin API schemas expose domain data without creating a speculative service or
  repository layer.
- Chapter reads derive scope from the server-owned current pointer. The browser
  cannot select an arbitrary manuscript version as current.
- A failed candidate remains visible in version history, while all current
  product reads continue to use the previous ready version.
- Existing UI components were wired instead of rebuilt.

Alternatives rejected for this lesson were fake queued responses, publishing on
upload, treating the newest list item as current, trusting Playwright mocks as
end-to-end evidence, and pulling future Story Bible/continuity/vector behavior
into the integration catch-up.

## Failure case observed by the developer

The developer uploaded valid v1 and v2 manuscripts, then an invalid UTF-8 v3.
Observed behavior:

```text
v3 version status = failed
v3 job safe error = The manuscript could not be parsed.
project current = v2
chapter count = 3
Manuscript UI = v2 chapter text
```

This is not rollback. v2 remains current because v3 was never published. The UI
therefore reflects PostgreSQL's current pointer rather than upload order.

The developer also encountered a missing future `config/litellm.yaml`: Docker's
short bind-mount syntax created a directory where Compose expected a file.
LiteLLM is not used in this lesson, so the current slice starts with
`docker compose up -d --build frontend worker`; Compose follows dependencies to
the backend, worker infrastructure, and storage/search services.

## Verification

- Backend unit/integration suite in Docker: 22 passed.
- Frontend Vitest: 5 passed.
- ESLint and Next.js production build passed.
- Mocked Playwright contract flows: 5 passed.
- Real Playwright flow without application API interception: 1 passed.
- The real flow crossed browser, FastAPI, PostgreSQL, MinIO, RabbitMQ, Taskiq,
  parser, Elasticsearch, job polling, and chapter rendering.
- Cross-project version/chapter access returned 404.
- A simulated RabbitMQ enqueue error returned a stable safe code without the raw
  exception or connection string.

The local real-browser flow completed in about three seconds, but this is a
single-machine smoke observation, not a latency SLA. There were no LLM calls,
API model charges, AI evaluations, or LangSmith traces.

## Security and reliability

- File type, size, non-empty content, filename, and UTF-8 parsing validation
  remain backend-enforced.
- Manuscript versions are filtered by project; chapters are filtered by the
  project's current ready version.
- Job responses expose only progress and safe error fields.
- A failed version cannot replace a known-good current version.
- Browser code never receives MinIO, RabbitMQ, Elasticsearch, or model-provider
  credentials.

Concurrent upload ordering, archival, project deletion cleanup, old-index
cleanup, and the full re-index lifecycle remain Lesson 10.3 work. Chapter-level
text is available now; paragraph/evidence anchors require later evidence
capabilities.

## Interview questions

1. What does a mocked browser API test prove, and what does it not prove?
2. Why should a newly uploaded manuscript not immediately become current?
3. How does atomic publication protect reads when candidate processing fails?
4. Why must chapter scope be derived and enforced on the server?
5. Why is polling PostgreSQL job state sufficient for this stage?
6. Which failures belong to FastAPI, Taskiq, PostgreSQL, MinIO, and Elasticsearch?
