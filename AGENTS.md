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
- fine-tuning
- multi-agent swarm
- GCP at the current course stage

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
