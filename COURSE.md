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

## Core portfolio scope

The core product flow is:

```text
Upload manuscript → browse Story Bible → ask questions with citations
→ review possible character-attribute contradictions
```

Learn RAG, bounded planning/tool use, evaluation, observability, grounding,
security, and reliability through this flow. Reuse the locked architecture and
completed implementations. A learning concept does not require a separate
service, graph node, model call, or product screen.

This curriculum defines required scope; broader designs in the specifications
are optional references where marked deferred. It does not change promoted AI
configurations or authorize implementing future lessons. AI behavior changes
still require prediction, baseline/candidate evaluation, developer interpretation,
and explicit promotion.

`COURSE_PROGRESS.md` remains the authoritative cursor. The 2026-09-11 revision
preserves completed Lessons 0–5, including 5.3, and the next lesson is 6.1.
Seven core lessons remain, followed by the requested practical fine-tuning
lesson 12.1 after the local application is complete. Do not reopen completed
lessons or require perfect full-book extraction or entity resolution before QA.

## Scope and stopping rules

- Freeze completed retrieval and story-memory expansion; fix defects blocking the core flow.
- Reuse one QA workflow and the existing Experiment Lab. A concept does not require its own agent, service, model, or screen.
- QA can use manuscript retrieval without a completed story-memory build. Missing extracted facts never prove an event did not happen.
- Citation ID validity and semantic support are different checks; retain both, bounded repair, and abstention.
- Each new experiment answers one concrete question. Reuse baseline cases and failure labels across lessons instead of restarting evaluation work.
- Start continuity with one character-attribute family, selected during lesson planning, and include legitimate changes and ambiguity as negative controls.
- Portfolio polish adds no new product capabilities. Keep experimental controls in the existing developer area.
- GCP/cloud deployment, AI CI/CD infrastructure, GTM/launch, and a multi-agent product are outside this course. Keep runnable tests and local regression evaluation.

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
  - leave version lifecycle hardening to Lesson 10.1 in the revised curriculum; advanced archival and old-index cleanup are deferred. Do not reopen this completed lesson.
- 3.2 Embeddings + vector retrieval
- 3.3 Hybrid retrieval with RRF
- 3.4 Cross-encoder reranking

## Phase 4 — Evaluation / Observability

- 4.1 LangSmith tracing
- 4.2 AI Experiment Lab

## Phase 5 — Structured Story Memory

Supported entities: characters/people, facilities/buildings, countries and
settlements, natural/geographical locations, organizations, and vehicles.
General artifacts and catch-all entities are out of scope for extraction,
resolution, Story Bible, and future continuity work. Scope is model-independent.

- 5.1 Entity extraction
- 5.2 Entity resolution
  - evaluate cached coreference groups with Gemma for unresolved candidates;
  - measure wall time, LLM calls, wrong/missed merges, review rate, and evidence;
  - preserve Stop/Resume and automatic application of accepted decisions;
  - defer Qwen comparison; code passing alone does not complete the lesson.
- 5.3 Facts / events / relationships

## Phase 6 — Model Gateway and Trade-offs

- **6.1 Model gateway and trade-offs**
  - inspect and extend the existing LiteLLM integration used by extraction and resolution; do not rebuild it;
  - compare one local and one API model on one existing task with the same fixed cases, measuring quality, structured-output reliability, latency, cost, and failures; do not add a model × prompt × provider matrix;
  - exercise one bounded provider fallback; distinguish provider retries from job retries;
  - preserve existing promoted configurations until an explicit experiment promotion.

## Phase 7 — Agentic Story QA

- **7.1 Grounded Story QA**
  - deliver a real Ask flow over existing retrieval with server-enforced project/version scope and SSE;
  - allow manuscript-backed QA when structured memory is unavailable or incomplete; expose relevant limitations without requiring a full memory rebuild;
  - include evidence-backed synthesis, citation validity and support verification, one repair, then removal or abstention;
  - use one shared QA backend for the Ask workspace and contextual panel; wire evidence navigation in this lesson;
  - establish direct QA and a small fixed evaluation baseline before adding planning.
- **7.2 Bounded planning and tools**
  - add structured decomposition and selection between manuscript search and existing story-memory tools;
  - use one bounded workflow with explicit execution state, validated tool arguments, and stopping conditions; do not require two agents to imitate an interview assignment;
  - combine routing decisions where practical; avoid a mandatory LLM call per concept;
  - enforce tool, retrieval, context, and LLM budgets, including bounded retrieval fallback;
  - compare direct retrieval against planning on multi-hop questions; trace selected tools, subquestions, cost, and failures without hidden chain-of-thought;
  - planning is required learning; activation policy is decided from the experiment, not assumed to improve every query.

## Phase 8 — QA and Agent Evaluation

- **8.1 QA and agent evaluation**
  - extend the existing Experiment Lab and the baseline established in 7.1–7.2 rather than building a second evaluation system;
  - cover factual, multi-hop, unanswerable, and adversarial questions with evidence labels;
  - measure answer quality, citation validity/support, hallucination, abstention, latency, and cost;
  - diagnose wrong tools, unnecessary planning, missing evidence, invalid arguments, and budget exhaustion separately from final-answer quality;
  - demonstrate detection of systematic regressions through fixed baseline comparisons and failure rates by question category; use local runs and existing traces, without a new monitoring dashboard or CI/CD system;
  - inspect traces and failures, compare controlled configurations, and let the developer interpret results and decide promotions;
  - keep fixed evaluation data separate from prompt tuning; report sample size and dataset limitations.

## Phase 9 — Focused Continuity

- **9.1 Focused continuity and feedback**
  - use existing facts to propose conflicting character attributes; verify both claims against manuscript evidence;
  - start with one character-attribute family, controlled contradictions and non-conflicts; do not build a general claim-routing taxonomy;
  - persist and display possible issues with two supporting passages; ambiguity is not a confirmed error;
  - reuse existing entity resolution and structured memory without expanding extraction scope;
  - connect writer verdicts and feedback to the real issue review flow;
  - evaluate controlled mutations and negative controls, including ambiguous or merely apparent contradictions;
  - measure precision, recall, F1, and false positives; discuss failures and use reviewed feedback for future evaluation cases.

## Phase 10 — Security / Reliability

- **10.1 Security and failure recovery**
  - exercise manuscript prompt injection, invalid tool arguments, project/version isolation, and safe error handling;
  - test dependency failures, duplicate jobs, idempotency, and bounded retries using existing protections;
  - inspect a real failure trace and explain recovery and remaining limits;
  - verify replacement uploads, stale-result fencing, and failed rebuilds preserving the current usable version;
  - reuse full rebuilds and version-pinned evidence; do not add incremental indexing or advanced archival;
  - prove the real browser-to-backend/storage/worker replacement flow.

## Phase 11 — Portfolio Finish

- **11.1 Portfolio finish and interview rehearsal**
  - polish the core desktop flows, citation navigation, progress, and empty/error/abstention states;
  - verify real upload, cited QA, issue review, and manuscript replacement without application API mocks;
  - demonstrate a successful answer, an abstention, a continuity finding, and an experiment comparison;
  - consolidate measured results and rehearse the request flow, one failed experiment, one reliability failure, and the purpose of each retained component;
  - rehearse the public Reedsy challenge: two-agent design, deterministic versus model decisions, systematic regression detection, style examples, and separate style/helpfulness evaluation; this is a design exercise, not another product feature or required challenge implementation;
  - prepare a repeatable local demo with a small manuscript and known supported, unanswerable, and continuity cases; distinguish demonstration fixtures from held-out evaluation data.

## Phase 12 — Practical Fine-tuning Lab

- **12.1 Small LoRA style experiment** — requested follow-on after 11.1, not a blocker for local application completion.
  - use one small model and one task: the style of a short editorial comment; no editor profiles, training screen, new service, or StoryGuard API;
  - at lesson planning, agree on the model, compatible training runtime, execution location, data rights, and memory/time/cost budget; this revision does not select a model, provision compute, or authorize training;
  - create a small versioned set of permitted examples with separate training, development, and held-out splits; keep related examples together to avoid leakage and keep the test set out of prompt and training selection;
  - compare the same base model with basic prompting, with few-shot prompting, and with a LoRA adapter on identical held-out inputs; keep decoding conditions comparable and record prompt/config versions;
  - assess style, helpfulness, preservation of supplied meaning, unsupported additions, inference latency, and training/inference resource costs; an automatic judge, if used, is checked against developer review;
  - reuse existing experiment conventions and reports, adding only the minimal script or notebook required for training/evaluation; do not build a second experiment platform;
  - follow prediction → discussion → experiment plan approval → baseline/candidate → developer interpretation → explicit promotion decision; a trained adapter never automatically replaces a promoted application model;
  - finish with a runnable adapter-loading example, recorded base-model/adapter/dataset/config provenance, a hands-on checkpoint, and a learning note after discussion; a negative result can complete the lesson.

After 11.1, record core application completion and advance the course cursor to
12.1 without starting training in the same turn. The requested course is fully
complete after 12.1 has both implementation and learning complete. Unrequested
optional labs below are never selected automatically.

## Original-topic mapping

This maps the previous unfinished syllabus to the revised course. Completed
lesson IDs and learning artifacts remain unchanged. Old future IDs below are
historical references, not additional lessons to execute.

| Previous topics | Revised destination |
| --- | --- |
| 6.1 gateway, 6.2 local/API experiment, 6.3 provider fallback | 6.1 Model gateway and trade-offs |
| 7.1 intent routing, 7.2 scoped retrieval, 8.1 synthesis, 8.2 verifier, 8.3 abstention, 11.1 QA integration | 7.1 Grounded Story QA; tool selection extends in 7.2 |
| 7.3 complexity/planning, 7.6 retrieval fallback/budgets | 7.2 Bounded planning and tools |
| 7.4 query rewriting, 7.5 conditional HyDE | Separate optional labs |
| 8.4 hallucination evaluation | 8.1 QA and agent evaluation |
| 9.1 mutations, 9.2 claim extraction/routing, 9.3 conflict verification | 9.1 Focused continuity and feedback, limited to character attributes |
| 9.4 continuity evaluation, 11.2 continuity integration | 9.1 Focused continuity and feedback |
| 10.1 injection, 10.2 retries/idempotency | 10.1 Security and failure recovery |
| 10.3 version/re-index lifecycle | 10.1 Security and failure recovery; advanced archival/cleanup deferred |
| 11.3 final experiment review, final QA/continuity hardening | 11.1 Portfolio finish and interview rehearsal |

The 2026-09-07 syllabus's 9.2 is now part of 9.1, and its 10.2 is now part of
10.1. These are merged responsibilities, not extra lessons or completed work.

---

## Integration sequencing rule

Connect user-visible capabilities in their lesson or an immediate catch-up lesson instead of postponing all UI/backend wiring to Phase 11. A catch-up lesson may add thin APIs and missing orchestration over completed capabilities, but it must not pull future domain or AI capabilities forward.

Security, evidence validation, and UI integration belong in each feature's first
usable slice. Phases 10–11 harden and verify them; they are not permission to
postpone safeguards or real UI wiring.

---

## Optional labs and deferred product work

- **Query rewriting**: compare raw queries against rewrites only after diagnosing retrieval misses.
- **HyDE**: a separate experiment when retrieval failures justify it; hypothetical text is never evidence.
- **Additional model/provider comparisons**: only for a measured quality or performance question. Existing model options remain available.

Deferred product work: product-help chat, checking pasted new text, broad
continuity (timeline, relationships, character knowledge, entity state,
locations, world rules, and catch-all issues), version comparison/restoration,
incremental indexing, advanced archival, and elaborate activity dashboards.
Existing entities, facts, relationships, and Timeline remain available; freeze
expansion and fix defects that block the core demo. Deferred UI paths must remain
explicitly unavailable or disabled until separately approved; their presence in
the shell does not create a core requirement.

GCP/cloud deployment, AI CI/CD/GTM, Kubernetes, Temporal, and a multi-agent
swarm are outside the planned course. Local Docker does not demonstrate cloud
deployment experience. Fine-tuning is limited to the requested post-core 12.1
experiment; product integration needs a separate proposal and promotion.
An unrequested optional lab never blocks core completion.

## Core completion criteria

- Supported QA answers open real manuscript evidence; insufficient evidence produces abstention.
- The Ask workspace and contextual panel use one backend; planning demonstrates bounded multi-step retrieval with inspectable tool calls and execution metadata.
- Manuscript-backed QA remains usable without complete structured memory; tool and planning failures are evaluated as well as final answers.
- Character-attribute issues show two supporting passages and accept writer feedback; ambiguous cases are not presented as confirmed errors.
- Fixed evaluation sets cover factual, multi-hop, unanswerable, adversarial, contradiction, and non-contradiction cases, separate from prompt tuning. Results include quality, latency, cost, and dataset limitations.
- Real browser checks cover upload, cited QA, issue review, and version replacement without intercepting application API calls.
- The developer can demonstrate a successful answer, abstention, continuity finding, and experiment comparison, and explain the request flow, one failed experiment, one reliability failure, and each retained component.
- Every core lesson has both `implementation_done = true` and `learning_done = true`. Passing code checks alone is insufficient.

Role references: [Reedsy AI Engineer posting](https://wellfound.com/jobs/3365364-ai-engineer-remote-europe) and [public challenge](https://github.com/reedsy/challenges/blob/main/ai-engineer.md), reviewed 2026-09-11. The course targets applied AI product engineering; it does not claim to cover every requirement of that role.
