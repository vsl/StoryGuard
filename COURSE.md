# StoryGuard AI Engineer Course

## How to use

Normal command:

```text
$storyguard-course-lesson
```

The skill reads `COURSE_PROGRESS.md` and automatically continues from the current lesson.

Do not manually specify the lesson unless you intentionally want to review/jump.

## Mandatory lesson flow

```text
1. Brief concept
2. Ask developer
3. Developer answers
4. Discuss right/wrong in chat
5. Correct mental model
6. Proposed implementation plan
7. Explicit developer approval
8. Implementation
9. Tests / traces / evals
10. Developer manual checkpoint
11. Discuss checkpoint
12. Learning note
13. Mark lesson complete
14. Advance COURSE_PROGRESS
```

Never skip the discussion/approval steps.

---

## Phase 0 — Foundation

- **0.1 System boundaries** — COMPLETED
- **0.2 Docker/local architecture** — COMPLETED

## Phase 1 — Application Backbone

- 1.1 FastAPI + PostgreSQL
- 1.2 MinIO + manuscript versions
- 1.3 Taskiq + RabbitMQ

## Phase 2 — Narrative Data

- 2.1 Hugging Face dataset lifecycle
- 2.2 Parsing / chapter / scene / chunking

## Phase 3 — Retrieval

- 3.1 BM25 baseline
- **3.1A Application API/UI integration catch-up**
  - audit production frontend data sources, test-only mocks, backend routes/schemas, completed domain workflows, and `docs/frontend-api-gaps.md`;
  - classify each UI path as already real, missing a thin API, missing integration orchestration over completed capabilities, or dependent on a future lesson;
  - verify project CRUD rather than rebuilding it;
  - connect manuscript upload/version history, job progress, basic success/failure version promotion, and parsed chapter viewing using capabilities from Lessons 1.1–3.1;
  - expose only aggregates supported by completed capabilities; keep later Story Bible, continuity, Story QA, vector/hybrid/reranker, LangSmith, and other future behavior explicitly unavailable or disabled;
  - prove one browser-to-backend/storage/worker vertical slice without intercepting or mocking its application API requests;
  - leave archival, old-index cleanup, concurrency hardening, and the full re-index lifecycle to Lesson 10.3; do not reopen completed lessons or implement other future capabilities.
- 3.2 Embeddings + vector retrieval
- 3.3 Hybrid retrieval with RRF
- 3.4 Cross-encoder reranking

## Phase 4 — Evaluation / Observability

- 4.1 LangSmith tracing
- 4.2 AI Experiment Lab

## Phase 5 — Structured Story Memory

- 5.1 Entity extraction
- 5.2 Entity resolution
- 5.3 Facts / events / relationships

## Phase 6 — Model Routing

- 6.1 LiteLLM gateway
- 6.2 Local vs OpenAI experiment
- 6.3 Failure / fallback routing

## Phase 7 — Agentic Story QA

- 7.1 Intent routing
- 7.2 Retrieval tools + scope
- 7.3 Complexity routing + query planner
- 7.4 Query rewriting
- 7.5 Conditional HyDE
- 7.6 Retrieval fallback + agent budgets

## Phase 8 — Grounding / Hallucination Control

- 8.1 Evidence-backed synthesis
- 8.2 Verifier
- 8.3 Abstention
- 8.4 Hallucination evaluation

## Phase 9 — Continuity Engine

- 9.1 Controlled mutation dataset
- 9.2 Claim extraction/routing
- 9.3 Conflict verification
- 9.4 Continuity evaluation

## Phase 10 — Security / Reliability

- 10.1 Prompt injection
- 10.2 Idempotency / retries
- 10.3 Manuscript version / re-index lifecycle

## Phase 11 — Integration

- 11.1 End-to-end Story QA
- 11.2 End-to-end Continuity
- 11.3 Final AI experiment review

---

## Integration sequencing rule

Connect user-visible capabilities in their lesson or an immediate catch-up lesson instead of postponing all UI/backend wiring to Phase 11. A catch-up lesson may add thin APIs and missing orchestration over completed capabilities, but it must not pull future domain or AI capabilities forward.

Phase 11 remains final end-to-end hardening of already integrated capabilities.

---

## Deliberately Not in Current Course

- GCP deployment
- go-to-market
- fine-tuning
- Kubernetes
- Temporal
- multi-agent swarm

Current focus: AI Engineering, AI workflows, agent-system design, RAG, evals, observability, security, reliability.
