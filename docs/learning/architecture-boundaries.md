# Lesson 0.1 — Product and architecture boundaries

## Status

- Implementation checkpoint: complete.
- Developer checkpoint: complete after clarifying PostgreSQL/MinIO/Elasticsearch and Taskiq/RabbitMQ/LangGraph boundaries.

## Problem

StoryGuard combines normal application code, background processing, retrieval, and AI workflows. Before implementation, each component needs one clear responsibility so that failures, security boundaries, and data ownership remain understandable.

## Selected design

- Next.js owns the browser UI and calls only FastAPI.
- FastAPI owns HTTP validation, CRUD, job enqueueing, and interactive SSE requests.
- PostgreSQL is the structured **source of truth**: projects, manuscript versions, job state, chapters, scenes, chunks, entities, facts, events, relationships, and evidence metadata.
- MinIO stores original manuscript files. It is authoritative for the uploaded object bytes, not for structured application state.
- Elasticsearch is a derived, rebuildable retrieval index containing scoped chunk text, metadata, and embeddings.
- Taskiq defines and publishes background jobs; RabbitMQ stores and delivers their messages; workers execute them.
- LangGraph orchestrates conditional/stateful AI workflows. It is not a queue and is not required for deterministic parsing.
- LiteLLM is the model gateway. Application code uses semantic model aliases rather than provider model IDs.
- LangSmith records AI traces and experiments but must not become a request dependency.

These boundaries are defined in `docs/specs/storyguard_backend_ai_spec.md`, especially sections 4, 7, 8, 10, 11, 14, 22, 25, and 44.

## Why this design

PostgreSQL provides transactions and durable structured state. MinIO handles large immutable file objects. Elasticsearch provides specialized BM25/vector retrieval and can be rebuilt from authoritative data. RabbitMQ keeps long work outside HTTP requests. LangGraph is reserved for AI flows that need routing, planning, fallback, verification, or abstention.

## Alternatives rejected

- Elasticsearch as the system of record: rejected because its documents are denormalized, derived, and rebuilt during version/index changes.
- Storing manuscript files in PostgreSQL: rejected because MinIO is the selected S3-compatible object store.
- Running manuscript ingestion synchronously in FastAPI: rejected because it would make HTTP requests long-running and fragile.
- Using LangGraph as a background queue: rejected because it manages workflow state, not durable task delivery.
- Calling an LLM directly from the frontend: rejected because it would expose secrets and bypass server-side routing, budgets, project/version scoping, citation validation, and security policies.

## Request and data flows

### Create project

```text
Browser -> Next.js -> FastAPI -> PostgreSQL -> FastAPI -> Browser
```

FastAPI validates the request and persists the project. Elasticsearch, MinIO, Taskiq, and LangGraph are not needed.

### Upload and process manuscript

```text
Browser -> Next.js -> FastAPI
  -> validate upload
  -> MinIO: store original file
  -> PostgreSQL: create manuscript_version + job_run
  -> Taskiq producer -> RabbitMQ -> Taskiq worker
  -> parse -> chapters/scenes/chunks
  -> PostgreSQL: structured data and job/version state
  -> embeddings -> Elasticsearch: retrieval index
  -> validate -> atomically publish READY version
```

Later course lessons add entity/fact/event extraction. These steps are not implemented prematurely in the Docker foundation.

### Ask StoryGuard

```text
Browser -> Next.js -> FastAPI -> LangGraph intent routing
  -> simple or complex path
  -> PostgreSQL structured retrieval and/or Elasticsearch manuscript retrieval
  -> optional reranker
  -> LiteLLM synthesis
  -> citation verification and repair/abstention
  -> FastAPI SSE -> Browser
```

Interactive Ask StoryGuard runs in FastAPI rather than Taskiq so progress and answer events can stream directly to the browser.

## Failure/debugging example

If Elasticsearch is unavailable, manuscript search and evidence retrieval fail, but existing project and manuscript-version records remain valid in PostgreSQL and original files remain in MinIO. This distinguishes a derived-index outage from data loss. The index can later be rebuilt from authoritative state.

If PostgreSQL is unavailable, the backend must not treat Elasticsearch results as replacement application state; project/version scoping, job state, and atomic publication cannot be trusted.

## Traces, metrics, latency, and cost

- LangSmith trace/run IDs: not applicable; no AI workflow exists yet.
- Evaluation metrics: not applicable for Lesson 0.1.
- Cost: no model calls.
- Latency trade-off: background ingestion adds queue delay but keeps HTTP upload responsive; interactive questions avoid Taskiq to support direct SSE streaming.

## Developer checkpoint result

The developer correctly identified the project-creation, manuscript-ingestion, and interactive-question paths. Two corrected points are retained for interview use:

1. PostgreSQL, not the original file or Elasticsearch, is the structured source of truth. MinIO owns file bytes; Elasticsearch is a rebuildable retrieval projection.
2. RabbitMQ delivers Taskiq jobs to workers. A worker may call LangGraph for conditional AI work, but RabbitMQ does not directly launch LangGraph and deterministic processing does not require it.

## Interview questions

1. **Why is Elasticsearch not StoryGuard's source of truth?**
   - It stores a denormalized retrieval projection, is version-scoped, and can be rebuilt from PostgreSQL/MinIO.
2. **What is the difference between RabbitMQ and LangGraph?**
   - RabbitMQ provides durable message delivery; LangGraph controls state and branching inside an AI workflow.
3. **Why does interactive Story QA run in FastAPI instead of Taskiq?**
   - FastAPI can stream progress and answer events directly over SSE without a second cross-process streaming channel.
4. **Why must the frontend call FastAPI instead of LiteLLM directly?**
   - The backend protects credentials and enforces routing, budgets, evidence validation, and project/version isolation.
5. **What happens when Elasticsearch and PostgreSQL disagree?**
   - PostgreSQL wins; the Elasticsearch index is treated as stale or invalid and rebuilt.
