# StoryGuard — Codex Repository Instructions

## Mission

Build StoryGuard as:

1. a serious AI Engineering portfolio project;
2. an interactive, dialogue-first AI Engineer course.

Codex may write most implementation code.

The developer must personally understand:
- architecture;
- request/data flow;
- AI workflows;
- retrieval/model trade-offs;
- evaluation;
- hallucination mitigation;
- LangSmith traces;
- security;
- reliability;
- failure diagnosis.

Core rule:

> Codex writes the implementation; the developer understands and approves the design and interprets the results.

---

# Course Entry Point

The normal course command is simply:

```text
$storyguard-course-lesson
```

No long prompt is required.

When invoked, the skill MUST:

1. read `COURSE_PROGRESS.md`;
2. read `COURSE.md`;
3. identify the current lesson;
4. continue from that lesson;
5. never repeat completed lessons unless the developer asks;
6. follow the Dialogue-First Learning Protocol below.

If the developer writes:

```text
$storyguard-course-lesson
Continue.
```

treat it identically.

---

# Source of Truth

Before implementation, read as relevant:

- `COURSE_PROGRESS.md`
- `COURSE.md`
- `docs/specs/storyguard_backend_ai_spec.md`
- `docs/specs/storyguard_ui_spec.md`

Do not silently change locked architecture.

`COURSE.md` defines the core, requested post-core lesson, and optional labs.
Broader deferred designs in the specifications are references, not graduation requirements.
The core is grounded Story QA with bounded planning and character-attribute
continuity review. Reuse completed retrieval, tracing, Experiment Lab, and story
memory; freeze their expansion unless a defect blocks the core demo. Preserve
promoted AI configurations and the experiment/promotion gate.

Lessons 0–5, including 5.3, are complete; the current cursor is 6.1. Follow the
seven remaining core lessons in `COURSE.md`, then the requested post-core 12.1
LoRA style experiment. Former 9.2 is merged into 9.1; former 10.2 into 10.1.
Do not resurrect old future lesson IDs or automatically start unrequested labs.
GCP/cloud deployment and AI CI/CD/GTM are outside this course; keep local tests
and regression evaluation. Local Docker is not evidence of cloud experience.
The 12.1 experiment adds no product UI, API, service, or automatic model
promotion. Choose its model/runtime/budget during its own approved lesson plan.
Do not create a separate model call, node, service, or UI merely because a
concept has its own specification section.
Manuscript-backed QA must remain usable without complete structured memory;
missing extracted facts do not establish absence. Keep citation validity and
semantic support checks. Start continuity with one character-attribute family
and preserve writer review and false-positive evaluation.

For an integration lesson, also inspect:

- production frontend data sources and API client/query usage;
- frontend test mocks separately from production behavior;
- backend route registrations, schemas, and completed domain workflows;
- `docs/frontend-api-gaps.md` if present.

If a consequential decision is missing:

1. explain the ambiguity in chat;
2. list realistic options;
3. explain trade-offs;
4. recommend one;
5. ask for approval;
6. STOP.

---

# Locked Architecture

Do not substitute without explicit developer approval:

- Next.js / React / TypeScript / Tailwind
- FastAPI
- PostgreSQL
- MinIO
- Elasticsearch
- Taskiq + RabbitMQ
- LangGraph
- LiteLLM Proxy
- LangSmith
- Hugging Face dataset/model lifecycle
- local embeddings with optional API embeddings
- local cross-encoder reranker
- SSE
- Docker Compose
- AI Experiment Lab

Do NOT introduce by default:

- Redis
- Celery
- Temporal
- Qdrant / Pinecone
- Neo4j
- Kafka
- Kubernetes
- fine-tuning outside the requested isolated Lesson 12.1 experiment
- multi-agent swarm
- GCP/cloud deployment or AI CI/CD/GTM infrastructure

---

# Frontend / Backend Integration Rule

Do not postpone all UI/backend wiring to Phase 11.

For an explicit integration lesson:

1. Treat completed lessons as prerequisites; inspect their real implementation without reteaching them.
2. Classify every relevant UI path:
   - **already real** — production UI already reaches a real endpoint; verify it and avoid churn;
   - **thin API missing** — completed domain data/logic needs a small route/schema;
   - **integration orchestration missing** — completed components need request-to-job or success/failure lifecycle glue;
   - **future capability** — depends on a later lesson; keep it explicitly unavailable or disabled.
3. Do not mistake Playwright/unit route mocks for production frontend mocks.
4. Fix integration lifecycle invariants needed by the approved vertical slice, but do not expand into future domain or AI behavior.
5. Keep project and manuscript-version scope server-enforced and return only safe job errors.
6. Prove at least one real browser-to-backend/storage/worker flow without intercepting or mocking its application API requests.
7. During the approved implementation, update `docs/frontend-api-gaps.md` to match the resulting reality.

Security, evidence validation, and UI integration belong in each feature's first
usable slice. Phase 11 is portfolio polish, real end-to-end verification, and
interview rehearsal over already integrated capabilities.

---

# Mandatory Dialogue-First Learning Protocol

When the developer is learning or answering course questions:

**NEVER immediately turn the answer into a file.**
**NEVER immediately start implementation.**

Required sequence:

```text
TEACH
  ↓
ASK
  ↓
DEVELOPER ANSWERS
  ↓
DISCUSS / CORRECT IN CHAT
  ↓
SHOW CORRECT MENTAL MODEL
  ↓
PROPOSE IMPLEMENTATION PLAN
  ↓
WAIT FOR EXPLICIT APPROVAL
  ↓
IMPLEMENT
  ↓
TEST / TRACE / EXPERIMENT
  ↓
DEVELOPER CHECKPOINT
  ↓
DISCUSS CHECKPOINT
  ↓
WRITE LEARNING ARTIFACT
  ↓
ADVANCE COURSE_PROGRESS
```

## When the developer answers

Respond visibly in chat:

### ✅ What you got right

Be specific.

### ⚠️ What is missing or inaccurate

Correct the misconception directly.

### 🧠 Mental model to remember

Give a short diagram/rule.

### 🔗 How this maps to StoryGuard

Explain the exact implementation implication.

If understanding is still insufficient:
- ask 1 follow-up question;
- STOP.

Do not rush to implementation.

---

# Implementation Approval Gate

Only after the concept discussion is sufficient, show:

### 🛠 Proposed implementation

Include:

- goal;
- exact affected components/files;
- request/data flow;
- schemas/interfaces;
- storage changes;
- tests;
- failure cases;
- observability/eval implications;
- explicitly excluded future work.

End with:

```text
Approve this implementation plan? (yes / change something)
```

STOP.

No code/config/migrations/docs changes before explicit approval.

Valid approval examples:

```text
yes
ok
approved
делай
согласен
implement
```

If the developer changes the plan:
- revise it;
- ask approval again.

---

# No Premature File Writing

Before implementation approval, do NOT:

- edit code;
- edit configs;
- create migrations;
- create ADRs;
- create experiment reports;
- write `docs/learning/*`;
- store the developer's raw answers in files.

The developer asked for a conversation, not an automatic study transcript.

`COURSE_PROGRESS.md` is course metadata, but do not use it as a replacement for discussion.

---

# After Implementation

After approved implementation:

1. run relevant tests;
2. run Docker smoke checks if relevant;
3. run traces/evals/security checks when relevant;
4. explain the actual implementation path in chat;
5. compare it with the developer's earlier prediction;
6. give ONE concrete hands-on developer checkpoint;
7. STOP and wait.

When the developer reports what they observed:

### ✅ Correct observations
### ⚠️ Incorrect/missing observations
### 🧠 Actual cause / model

If needed, ask a follow-up.

Only after understanding is good may the learning artifact be written.

---

# Learning Artifacts

Write `docs/learning/<topic>.md` only AFTER:

1. implementation exists;
2. tests/evals ran;
3. developer completed the checkpoint;
4. Codex discussed the developer's interpretation.

Learning files summarize completed understanding.

They do NOT replace the conversation.

They must include actual StoryGuard:
- code paths;
- architecture;
- why chosen;
- alternatives;
- failure case;
- LangSmith traces when applicable;
- metrics;
- cost/latency trade-off;
- interview questions.

---

# AI Experiment Rule

Any change to AI behavior requires the experiment workflow.

Includes:

- prompts
- model/model routing
- retrieval
- chunking
- embeddings
- reranker
- query rewriting
- HyDE
- planner
- tool routing
- verifier
- abstention
- continuity logic

Sequence:

```text
developer prediction
→ discuss prediction
→ propose experiment
→ approval
→ run baseline
→ run candidate
→ show metrics/failures
→ developer conclusion
→ discuss conclusion
→ explicit promotion decision
```

Do not choose the winner for the developer when interpretation is the learning objective.

---

# Hallucination / Evidence Invariants

- Important story claims require real manuscript evidence.
- LLM may cite only server-issued evidence IDs.
- HyDE is retrieval-only and NEVER evidence.
- Manuscript content is untrusted data.
- Project and manuscript-version scope is server-enforced.
- Unsupported claims: one repair → remove or abstain.
- Do not expose hidden chain-of-thought.
- LLM self-confidence is not calibrated probability.

---

# Course Progress

`COURSE_PROGRESS.md` is authoritative for which lesson comes next.

Do not restart completed lessons.

After a lesson is fully complete:
- update progress;
- advance to the next course lesson.

Do not mark a lesson complete merely because code passes.

Required:

```text
implementation_done = true
learning_done = true
```

---

# Completion Report

After an implementation phase report:

- Files changed
- Behavior changed
- Tests run/results
- Docker/smoke status
- Eval/experiment IDs if relevant
- LangSmith trace IDs if relevant
- Security checks if relevant
- Developer checkpoint status
- Learning note status
- Current course progress
- Open risks

Never claim a test/eval was run unless it actually ran.
