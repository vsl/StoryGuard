# MinIO + Manuscript Versions

## Mental model

```text
MinIO      = authoritative original file bytes
PostgreSQL = authoritative version metadata, state, and current pointer

uploaded != ready
ready + validated -> eligible to become current
```

A StoryGuard manuscript version is a domain record in PostgreSQL. It is not the
same thing as MinIO/S3 bucket versioning. Each original file uses an immutable,
server-generated object key:

```text
projects/{project_id}/manuscripts/{manuscript_version_id}/original.{extension}
```

## StoryGuard implementation

- `backend/app/manuscripts.py` validates the upload, removes path components from
  the original filename, enforces the configured size limit, calculates SHA-256,
  writes the stream to MinIO, and creates the version record.
- `backend/app/db/models/manuscript_version.py` stores version number, status,
  object key, filename, MIME type, size, hash, pipeline version, and timestamps.
- `backend/app/db/models/project.py` stores the nullable
  `current_manuscript_version_id` pointer.
- `backend/migrations/versions/20260822_02_create_manuscript_versions.py` creates
  the table, constraints, index, and current-version foreign key.
- `compose.yaml` provides backend-only MinIO credentials, a private bucket name,
  and a configurable 50 MiB default upload limit.

Creation flow:

```text
file stream
-> validate extension, MIME type, size, and non-empty content
-> sanitize original filename and calculate SHA-256
-> lock the project row and allocate its next version number
-> upload bytes to the private MinIO bucket
-> insert manuscript_versions(status=uploaded)
-> commit without changing project.current_manuscript_version_id
```

The synchronous MinIO SDK call runs through `asyncio.to_thread()` so it does not
block FastAPI's event loop. A project-row lock serializes concurrent version-number
allocation for the same project.

## Why this design

- Large immutable files belong in object storage; queryable state belongs in
  PostgreSQL.
- Server-generated keys prevent client-controlled storage paths, collisions, and
  cross-project placement.
- Upload does not publish a version. Until processing succeeds, an existing ready
  version remains current.
- PostgreSQL blobs, client-selected object keys, publication on upload, and a
  storage interface with only one implementation were rejected.
- The public upload endpoint is deferred until Lesson 1.3 can return a real Taskiq
  `job_id` instead of a fake queued state.

## Failure case

If MinIO upload fails, the database transaction rolls back and no version record is
created. If PostgreSQL fails after MinIO accepts the object, StoryGuard rolls back
and attempts to remove the object. That compensation is best-effort because MinIO
and PostgreSQL do not share a distributed transaction; a failed cleanup is logged
as an orphan risk.

If v3 is current and v4 is only uploaded or later fails processing, queries still
use v3. There is no rollback to v3 because the pointer was never changed.

## Verification and observations

- Full backend unit/integration suite: 8 passed, 0 failed.
- Developer checkpoint: the real PostgreSQL + MinIO round trip passed.
- The retrieved MinIO bytes exactly matched the uploaded bytes.
- PostgreSQL stored `status=uploaded` and the expected SHA-256 hash.
- `current_manuscript_version_id` remained unset after upload.
- Alembic revision `20260822_02` is at head.
- Docker readiness reported PostgreSQL, MinIO, and Elasticsearch up.

This lesson has no LLM calls, LangSmith traces, AI evaluation metrics, or model
cost. Hashing and upload add linear file-size latency; no optimization is justified
without measurements.

## Security and reliability

- The bucket is private and credentials remain backend-only.
- Accepted v1 formats are `.docx`, `.md`, and `.txt`; extension and MIME type must
  agree with the allowlist.
- The backend ignores client path components when retaining the original filename.
- Database constraints protect allowed statuses, positive sizes/version numbers,
  unique project version numbers, and unique object keys.
- File signatures and defensive `.docx` ZIP parsing belong to the parsing lesson.

## Interview questions

1. Why should object bytes and manuscript-version metadata use different stores?
2. Why must uploading a new manuscript not immediately make it current?
3. How do server-generated object keys improve project isolation and security?
4. How can an application handle failure across PostgreSQL and object storage
   without a shared transaction?
5. Why is application-level manuscript versioning different from S3 object
   versioning?
