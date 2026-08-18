# StoryGuard AI Engineer Course

## Goal

Codex writes most implementation code. The developer must still finish able to draw the architecture, trace requests, debug LangSmith traces, design/interpret evals, compare models and retrieval strategies, explain hallucination mitigation, and answer AI Engineer interview questions in English.

Each lesson follows:

```text
Concept briefing
-> Architecture checkpoint
-> Codex implementation
-> Tests
-> Developer inspection
-> Hands-on experiment/debug task
-> Learning note
-> Interview questions
-> Lesson complete
```

A lesson is complete only when both implementation and learning checkpoints are complete.

# Phase 0 — Foundation

## Lesson 0.1 — Product and architecture boundaries
Learn Browser/Frontend/FastAPI/PostgreSQL/Elasticsearch/Taskiq/RabbitMQ/LangGraph/LiteLLM/LangSmith boundaries. Codex verifies repo skeleton. Developer redraws system without the spec.

## Lesson 0.2 — Docker local system
Codex builds local service skeleton. Developer stops one dependency and predicts/observes the failure boundary.

# Phase 1 — Deterministic application backbone

## Lesson 1.1 — FastAPI + PostgreSQL
Codex implements project CRUD. Developer traces one HTTP request to SQL.

## Lesson 1.2 — MinIO + manuscript versions
Codex implements file/object metadata flow. Developer explains object storage vs DB metadata and atomic publish.

## Lesson 1.3 — Taskiq + RabbitMQ
Codex implements one background ingestion task. Developer intentionally triggers a worker failure and inspects retry/idempotency behavior.

# Phase 2 — Real narrative data

## Lesson 2.1 — Hugging Face data lifecycle
Datasets: `common-pile/project_gutenberg`, `meithnav/narrativeqa`, `illuin-conteb/narrative-qa`. Codex adds pinned dataset registry/bootstrap. Developer inspects dataset metadata and explains the distinct role of each dataset.

## Lesson 2.2 — Parsing, chapters, scenes, chunks
Codex parses a selected public-domain manuscript using our deterministic rules. Developer manually inspects chunks and identifies at least one poor boundary.

# Phase 3 — Retrieval from first principles

## Lesson 3.1 — BM25 baseline
Codex implements Elasticsearch BM25 and eval runner. Developer runs Recall@10 and manually explains three misses. No vector retrieval yet.

## Lesson 3.2 — Embeddings + vector search
Codex adds local EmbeddingGemma/vector retrieval. Developer compares the same dataset against BM25 and explains which query types improved/worsened.

## Lesson 3.3 — Hybrid RRF
Codex adds RRF. Developer interprets the same retrieval eval and explains a query where lexical+semantic fusion helps.

## Lesson 3.4 — Local cross-encoder reranker
Codex adds BGE reranker. Developer compares quality and p95 latency and inspects one changed ranking.

# Phase 4 — Evaluation and observability

## Lesson 4.1 — LangSmith tracing
Codex instruments the retrieval path. Developer opens a real trace and reconstructs the request flow.

## Lesson 4.2 — AI Experiment Lab
Codex implements the Experiment Lab backend and first developer UI. Developer personally chooses the retrieval winner from metrics + failure examples and writes the conclusion.

# Phase 5 — Structured Story Memory

## Lesson 5.1 — Entity extraction
Codex adds structured extraction with evidence. Developer inspects schema validation/repair.

## Lesson 5.2 — Entity resolution
Codex implements aliases/candidates/human review. Developer evaluates ambiguous identity cases and false-merge risk.

## Lesson 5.3 — Facts, events, relationships
Codex persists structured story memory with provenance. Developer traces one fact back to exact manuscript evidence.

# Phase 6 — Model routing

## Lesson 6.1 — LiteLLM gateway
Codex configures semantic aliases and local/OpenAI providers. Developer explains why business logic never contains raw provider model IDs.

## Lesson 6.2 — Local vs API model experiment
Codex prepares the experiment. Developer runs/reads quality, latency, and cost and decides which tasks should remain local.

## Lesson 6.3 — Fallback
Codex tests fallback. Developer disables the local provider and inspects retry/fallback traces.

# Phase 7 — Agentic Story QA

## Lesson 7.1 — Intent routing
Codex implements PRODUCT_HELP/STORY_QA/CONTINUITY/CHECK_TEXT routing with structured output. Developer builds adversarial routing examples.

## Lesson 7.2 — Retrieval tools and tool scoping
Codex exposes read-only tools. Developer proves Project A cannot retrieve Project B.

## Lesson 7.3 — Complexity routing + planner
Codex adds planner only for complex/multi-hop questions. Developer reviews several plans and identifies over/under-decomposition.

## Lesson 7.4 — Query rewriting
Codex adds rewriting. Developer runs raw-vs-rewritten retrieval experiment.

## Lesson 7.5 — Conditional HyDE
Codex implements fallback-only HyDE. Developer finds one case where it helps and one where it does not, and confirms HyDE is never evidence.

## Lesson 7.6 — Retrieval fallback + budgets
Codex implements evidence-coverage checks and hard limits. Developer forces insufficient evidence and inspects fallback/abstention.

# Phase 8 — Grounded generation and hallucination control

## Lesson 8.1 — Evidence-backed synthesis
Codex enforces server-issued evidence IDs. Developer attempts a fake citation and observes rejection.

## Lesson 8.2 — Verifier
Codex implements draft -> verify -> one repair -> verify. Developer inspects an unsupported claim trace.

## Lesson 8.3 — Abstention
Codex builds no-answer evals. Developer explains why abstention can be the correct result.

## Lesson 8.4 — Hallucination evaluation
Codex instruments answer correctness/citation support/hallucination rate. Developer manually labels a sample and compares to automated evaluators.

# Phase 9 — Continuity engine

## Lesson 9.1 — Controlled mutation dataset
Codex generates continuity mutations and negative controls from public-domain fixtures. Developer reviews validity.

## Lesson 9.2 — Claim extraction/routing
Codex implements claim types/routes. Developer explains which source/retrieval path serves each claim type.

## Lesson 9.3 — Conflict verification
Codex adds verifier + issue persistence. Developer inspects false positives and proposes an improvement.

## Lesson 9.4 — Continuity evaluation
Codex runs precision/recall/F1. Developer decides whether an experimental change should be accepted.

# Phase 10 — Security and reliability

## Lesson 10.1 — Prompt injection
Codex adds adversarial manuscript tests. Developer inspects one malicious passage through a real trace.

## Lesson 10.2 — Idempotency/retries
Codex adds duplicate delivery tests. Developer proves duplicate jobs do not duplicate facts.

## Lesson 10.3 — Re-index/version lifecycle
Codex implements full re-index + atomic publish. Developer creates v1/v2 changes and proves old chunks cannot leak.

# Phase 11 — Integration

## Lesson 11.1 — End-to-end Story QA
Developer traces one complex browser question through routing/planning/retrieval/reranking/generation/verification/citations.

## Lesson 11.2 — End-to-end continuity
Developer traces one issue from source text to UI.

## Lesson 11.3 — Final AI experiment review
Use Experiment Lab to review key architectural choices and prepare interview explanations.

# Deliberately postponed

```text
GCP deployment
production go-to-market loop
fine-tuning
Kubernetes
Temporal
multi-agent swarm
```

The current course deliberately prioritizes AI workflows, RAG, agents, evaluation, observability, security, and model routing over DevOps.
