# Frontend / Backend API Gap Matrix

Implementation snapshot: 2026-09-07, including Lesson 5.3 structured story memory
and its post-implementation review. Scope classification updated 2026-09-11 for
the approved seven-lesson core and post-core LoRA experiment; this documentation
revision changes no endpoints or UI behavior. Historical verification below is
not a new test run. Lesson 5.3 is complete and the current cursor is 6.1.

The frontend is wired to the contracts in the backend and UI specifications.
This document records what the repository actually publishes today. “Missing”
means the UI displays an explicit unavailable state; it does not imply a hidden
mock implementation.

## Available now

Current scope is characters/people, facilities/buildings, countries/settlements,
natural/geographical locations, organizations, and vehicles. General artifacts
and catch-all entities are no longer extracted, accepted by the API, or shown
as Story Bible tabs. Gemma is unchanged. Extraction uses prompt V3 and GLiNER
label schema V2; older verification sections below describe historical runs.

The developer-promoted resolution path is now xCoRe + Gemma. An isolated Python
runtime inside the worker scans original chapter windows and caches complete
results per version/content/model pipeline. Exact aligned links skip Gemma;
remaining candidate pairs use Gemma. Both paths preserve evidence and conflict
checks. The API exposes `pipeline`, `coreference_merge_count` (actually applied),
and `gemma_comparison_count` (distinct evaluated pairs, not HTTP request count).
The UI shows these counts and coreference-stage elapsed time. Stop kills an
unfinished scan; completed caches and saved decisions survive Resume. Failure
or the 30-minute scan limit triggers a visible Gemma fallback. Existing Gemma
timeouts and the candidate ceiling remain. Bounded worker batches now continue
automatically; the user does not have to Resume after each work limit. Full-book
speedup is not established.

### Structured story memory (2026-09-06)

After entity resolution completes, Story Bible and Timeline can explicitly
start a version-pinned background build. Taskiq sends the job through RabbitMQ;
the worker supplies each manuscript chunk, its server-issued evidence block,
and only the resolved entities present in that chunk to structured-memory prompt
V7. Validated facts, events, relationships, citations, chunk coverage, prompt
version, model alias, latency and token usage are stored in PostgreSQL. The read
APIs expose only the current project/version and the latest usable run.

Relationship changes are event-backed: a start event initializes a relationship,
and a later end event updates that row with `end_event_id` and `status=ended`.
Both events remain independently queryable. Exact duplicates from overlapping
chunks are collapsed. Invalid model output gets one repair; a still-invalid
chunk is omitted and counted, without leaking raw errors or replacing the last
usable run. A changed manuscript version or entity-resolution state fences the
worker before, during, and immediately before completing extraction. The
resolution fingerprint includes entity state, raw aliases, mention assignments,
surface text and source spans. Read APIs hide runs from older fingerprints.
Retries cannot replace a usable run unless they preserve every previously
successful chunk; succeeding on a different number-equivalent set is not an
improvement.

Verification: the full backend suite ran 120 tests against PostgreSQL with two
optional skips; focused lifecycle tests cover start-to-end updates, evidence
offsets, scope, idempotency, stale fingerprints, partial failure, non-regressive
chunk sets and safe errors. All 21 frontend tests, formatting, ESLint, TypeScript
and the Next.js production build passed. A real browser run without application
API interception exercised UI → API → RabbitMQ/Taskiq → V7 via LiteLLM →
PostgreSQL → Story Bible/Timeline/Manuscript. The current model safely omitted
the wedding chunk, accepted the divorce event, and removed the associated
relationship after one repair because its event omitted both entity roles. The
UI showed `1/2 chunks`, the partial-failure warning, chronological and narrative
time, Timeline evidence, and an exact source-range highlight. This is a
functional and fail-closed smoke check, not an accuracy benchmark; relationship
recall remains a measured AI-quality risk rather than a silently relaxed
validator.

The promoted V7 experiment recorded semantic macro F1 0.715 with 1/12 failed
cases; the stricter V8 semantic verifier regressed to 0.200 with 9/12 failures
and was not promoted. LangSmith tracing was disabled for the local smoke, so no
trace ID exists. Transport failures now report zero repair attempts in the
experiment metrics instead of inventing a repair call. A clean Compose image
rebuild remains unverified because Docker Hub timed out while resolving
`python:3.14.4-slim`; the same-dependency local images were run with current-code
overlays instead.

### Story Bible navigation correction (2026-09-01)

The desktop Story Bible now gives the entity list and detail area independent
scroll containers. Selecting an entity preserves the list position, resets only
the detail pane, and renders the selected entity before the resolution
workspace. Search remains sticky in the list. Mobile keeps the single-column
flow. Canonical names are filtered from API aliases after normalized comparison;
the original alias rows remain in PostgreSQL for evidence/audit and reversal.
No route, schema, migration, model or resolution rule changed.

Verification: the full PostgreSQL-backed backend suite passed 95 tests (93
passed, 2 optional skips). Frontend unit coverage includes pane independence,
entity-before-resolution order, URL selection and detail-pane reset; ESLint,
TypeScript and both production Docker builds passed. A read-only browser check
against the real `the railway children` page measured separate 600px scroll
areas (`overflow: auto`), scrolled the detail pane to 900px, selected `Aunt
Emma`, and observed the detail pane return to 0 while the character list stayed
independent. After the backend update, the `Aunt Emma` detail contained no
duplicate Aliases label. Only the frontend and API backend were replaced; the
separate active resolution worker remained up and its job advanced from 343 to
348 of 2,000 during verification.

### Resolution batch observability verification (2026-08-31)

Every worker slice now creates an `entity_resolution_batch` LangSmith trace.
Automatic continuations and manual Resume share the job ID and increment the
batch number. Gemma comparisons and a lightweight `resolution_coreference`
cache/scan stage are children; fresh subprocess inference is linked by
`source_scan_trace_id`. A cache hit references the original scan rather than
claiming its old load/inference duration as new work.

Batch outputs distinguish attempts, retries, failures and stop/continuation
reasons from committed `version_totals`. Those totals are cumulative snapshots,
not per-batch deltas: do not add them across batches. A model `merge` prediction
is not itself a saved merge; `merge_decisions_applied` counts committed decisions.
Candidate audit metadata stores `batch_trace_id`; the existing API's pair trace
ID remains the comparison/scan ID. No new route, UI field or migration was added.

The new batch/cache spans contain only identifiers, counts, timings and safe
codes, in every content mode. Existing Gemma tracing still obeys
`LANGSMITH_TRACE_CONTENT`; the local stack remains in `full` mode, which includes
manuscript excerpts in Gemma inputs. Tracing failures cannot prevent saving
decisions. Raw database/queue exception text is excluded from the new spans;
the database remains the audit source of truth if trace delivery fails.

Verification on the rebuilt/deployed backend and worker:

- Full backend suite against PostgreSQL: 95 tests, 93 passed, 2 optional skips.
  Tests cover parent/child linkage across automatic batches, cache hits, stop,
  retries, queue failure, committed totals, privacy modes and exporter outages.
  Routine tests disable live export; tracing assertions use a fake client.
- The separately enabled slow deadline regression passed in 61.203 seconds.
- Real browser smoke passed in 58.3 seconds without application API mocks:
  upload, Stop/Resume, one xCoRe merge, one Gemma merge, refreshed aliases and
  source evidence. This small fixture does not cross the production batch
  limit; automatic handoff is covered by the database tests.
- LangSmith delivery was verified by reading the stored roots and their child
  runs through the configured SDK, not merely checking local trace IDs.
  Smoke job: `03f6fa37-8674-465e-ad4c-e2bfeb31e3d4`.
  [Batch 1: stopped](https://smith.langchain.com/o/6a1c43b4-612e-4749-924e-498d5f684b5b/projects/p/b93796b7-f989-4ba8-b64d-60438beef543/r/01a0589d-9ce3-75c2-936e-981d3e5a2559?poll=true)
  took 13.210 seconds, saved one coreference merge, and ended `user_stopped`;
  its cancelled Gemma child is marked failed, not a persisted pair failure.
  [Batch 2: completed](https://smith.langchain.com/o/6a1c43b4-612e-4749-924e-498d5f684b5b/projects/p/b93796b7-f989-4ba8-b64d-60438beef543/r/01a0589d-d1cc-7763-aad6-aab30b201ef2?poll=true)
  took 27.363 seconds, reused the cache, attempted Gemma once, and ended
  `no_eligible_pairs`: two total saved merges and zero errors/review/pending.
  Gemma child: `01a0589d-d550-7022-8ec9-751945bbf7b7` (26.453 seconds).
  Original scan: `01a0589d-9fe2-7521-a1bd-33a611a8290c`.
- Backend readiness returned HTTP 200; infrastructure was healthy and the
  worker/frontend running. Disposable DB/project/upload/index records were
  cleaned up by the test. The retained user project, `the railway children`,
  and its two completed jobs remain. No user job was restarted or interrupted.
- All 15 frontend unit tests, ESLint, TypeScript and `git diff --check` passed.
  Frontend source was unchanged in this tracing step.

Changed implementation: `backend/app/ai/{tracing,entity_resolution,coreference}.py`
and `backend/app/queue/tasks/entity_resolution.py`, with regression coverage in
`backend/tests/{test_entity_resolution,test_coreference,test_retrieval}.py` and
the backend observability specification. No dependency, model, prompt, candidate
policy or quality evaluation changed. The 2,000-candidate ceiling and known
coreference false-merge risk remain; this smoke is not full-book accuracy or
speed evidence. Existing historical traces are not reconstructed.

The later developer checkpoint inspected both correlated batches, resolved the
cumulative-count/cache interpretation, and verified the Story Bible navigation.
Lesson 5.2 is complete; its learning summary is
`docs/learning/entity-resolution.md`, and the course now points to Lesson 5.3.

### Automatic batch continuation verification (2026-08-31)

Repository implementation: `backend/app/entity_resolution.py` uses persisted
attempt counts for retry eligibility; `backend/app/queue/tasks/entity_resolution.py`
queues the next batch under the same job ID. Queued timestamps and attempt
numbers prevent late dispatch errors from overwriting Stop/Resume. The frontend
keeps Stop enabled across queue handoffs and explains that work continues when
the page is closed. No schema migration, service, model or prompt was added.

Local verification: backend discovery ran 92 tests, with 49 passing and 43
database/optional tests skipped. All 15 frontend tests, lint, TypeScript and the
production build passed. New database regressions cover automatic handoff
without another start request, retry exhaustion across six batches, queue
failure preserving saved merges, and Stop/Resume during a late enqueue failure.
After the approval service's usage limit initially blocked Docker access, the
developer approved retrying verification/deployment. Clean backend, worker and
frontend image builds passed. The updated backend suite ran against PostgreSQL:
92 tests, 90 passed and 2 optional skips. The optional 61-second deadline test
was then run separately and passed in 61.316 seconds, confirming that a pair can
finish past the batch budget and the remaining work is queued automatically.
The database continuation tests mock inference and queue delivery; the real
browser smoke separately passed in about one minute without application API
interception, covering upload, Stop/Resume, automatic merges, aliases and source
evidence. That tiny browser fixture does not cross the production batch limit.

The tested backend, worker and frontend images are deployed. Backend readiness
returns HTTP 200, infrastructure health checks pass, and the worker/frontend
are running. Test records were cleaned up; the retained user project and its
two completed jobs remain. No active user job was interrupted during deployment.

Existing books and jobs were not modified or restarted. The 2,000-candidate
discovery ceiling remains; automatic continuation does not imply full alias
coverage. No model-quality experiment was run; trace IDs from the live smoke were
not captured. Course 5.2, developer checkpoint and learning-note status remain
unchanged. For the previously completed/budget-limited book run, refresh the UI
and press Resume once; subsequent batch handoffs require no further clicks.

### Combined pipeline verification (2026-08-31)

The final image passed 88 backend tests (86 passed, 2 optional skips); all 14
frontend tests, lint, TypeScript and production builds passed. The real browser
test passed in 52.6 seconds with no application API interception: GLiNER upload,
one xCoRe merge without Gemma, one Gemma fallback pair, Stop/Resume, two applied
merges, no errors, updated aliases and source evidence. The first browser
fixture produced no xCoRe link and used Gemma correctly; the final functional
fixture explicitly states same-person identity to exercise both routes. This
fixture check is not an accuracy benchmark. Restricted native/Docker model
loading reproduced all five original diagnostic groups exactly.

No database reset was performed during promotion. The disposable browser
projects were removed, preserving the existing user project and its jobs.
Promotion details, earlier failures and trace IDs are in
`docs/experiments/2026-08-31-coreference-gemma-promotion.md`. Course 5.2 and its
developer checkpoint/learning note remain unchanged.

### Scope cleanup verification (2026-08-31)

The developer authorized resetting disposable test data without backup. Only
the `storyguard` PostgreSQL database was dropped/recreated after stopping the
backend and worker. It previously held one project and 6,287 mentions; those
application records and decisions are gone. Other databases, Docker volumes,
MinIO uploads, search-index data, model caches and local test-book files were
not deleted. Old derived storage remains inaccessible through new project IDs.

Migration `20260831_12` installs the six-category constraints. It fails on
incompatible populated databases rather than silently deleting rows. Downgrade
likewise refuses rows that do not fit the old taxonomy. No backup/migration
framework was added for this explicitly disposable iteration.

Verification: 83 backend tests ran against PostgreSQL, 81 passed and 2 optional
tests were skipped; all 14 frontend unit tests, lint, TypeScript and container
builds passed. `alembic check` reports no new operations (the existing cyclic
project/version FK warning remains). The real browser test passed in 1.1 minutes:
upload through GLiNER, verify six tabs/no Objects tab, query the six-category API,
reject an unsupported type, start Gemma, Stop/Resume, automatic merge and source
evidence. No application API calls were mocked. Its disposable project was
removed, leaving the fresh application database empty.

This verifies functionality, not extraction/coreference accuracy or speed.
Historical metrics below were not rerun or rewritten. Course progress and the
developer learning checkpoint remain unchanged.

| Capability | Endpoint | UI behavior |
| --- | --- | --- |
| List projects | `GET /api/projects` | Project list works. |
| Create project | `POST /api/projects` | Create form works and redirects to upload. |
| Project detail | `GET /api/projects/{project_id}` | Project shell and settings load. |
| Edit project | `PATCH /api/projects/{project_id}` | Title, description, and language settings work. |
| Delete project | `DELETE /api/projects/{project_id}` | Confirmation and deletion work. |
| Extractor choices | `GET /api/extraction-models` | Server-owned Gemma (default), GLiNER2.5 Base and Qwen3.5 9B choices. |
| Upload manuscript | `POST /api/projects/{project_id}/manuscripts` | Multipart `extraction_model` is optional (Gemma default). The chosen ID is stored on the version, returned in upload/version responses, and used by the worker on retries. Parsing, indexing and entity extraction are real. |
| Version history/detail | `GET /api/projects/{project_id}/manuscripts`, `GET /api/projects/{project_id}/manuscripts/{version_id}` | Version status and the actual current version are visible. |
| Cancel manuscript processing | `POST /api/projects/{project_id}/manuscripts/{version_id}/cancel` | Cancel processing is available on uploaded/processing rows, including after reload. The server checks project/version scope, returns the updated version, treats repeated cancellation as success, and returns 409 for completed/failed versions. History polls while work is unfinished. |
| Job progress | `GET /api/jobs/{job_id}` | Upload UI polls state, safe errors, current-stage elapsed time, and accumulated per-stage durations. |
| Parsed chapters | `GET /api/projects/{project_id}/chapters`, `GET /api/projects/{project_id}/chapters/{chapter_id}` | Read-only chapter list and text use the project's current ready version. |
| Resolve extracted mentions | `POST /api/projects/{project_id}/entity-resolution/run` | Explicit, version-pinned Story Bible action runs the selected resolution pipeline independently of the upload extractor. One start automatically continues across time/call-limited worker batches. No re-upload, re-extraction or repeated Resume clicks are needed. |
| Stop/resume resolution | `POST /api/projects/{project_id}/entity-resolution/jobs/{job_id}/stop`, existing `/entity-resolution/run` | Story Bible exposes Stop while queued/running, including between automatic batches, and Resume after stopping or a job failure. Stop is project/version/job scoped and idempotent, preserves saved work, and fences late model results and enqueue failures. |
| Resolution review | `GET /api/projects/{project_id}/entity-resolution/candidates`, `POST /api/projects/{project_id}/entity-resolution/{candidate_id}/resolve` | Automatic merging is ON by default. Eligible decisions apply immediately in the same transaction as the model prediction; applied pairs leave the list and character/detail queries refresh during processing. Genuine uncertainty/conflicts and technical errors have separate counters. Failed cards show a safe cause, elapsed time, attempt, and trace ID when available. |
| Characters and aliases | `GET /api/projects/{project_id}/characters`, `GET /api/projects/{project_id}/characters/{entity_id}` | Current-version identity anchors appear after resolution initializes them. Applied merges group aliases and source evidence. Original mentions remain intact; attributes and facts are not invented. |
| All supported entities | `GET /api/projects/{project_id}/entities?type=...`, `/entities/{entity_id}` | The same names, aliases and evidence flow for all six entity categories; unsupported types return 422 and cross-project IDs return 404. |
| Build story memory | `POST /api/projects/{project_id}/structured-memory/run`, `GET /api/projects/{project_id}/structured-memory/status` | Story Bible and Timeline start, poll, retry or rebuild the current resolved manuscript version and show chunk coverage plus safe partial-failure status. |
| Facts | `GET /api/projects/{project_id}/facts` | Current-run fact list and embedded manuscript evidence. |
| Events/timeline | `GET /api/projects/{project_id}/events` | Event list with chronological and narrative order, participants, locations and embedded evidence. |
| Relationships | `GET /api/projects/{project_id}/relationships` | Event-backed active/ended relationship rows and embedded evidence. |
| Direct search | `GET /api/projects/{project_id}/search?q=...&rerank=...` | Project search uses the current ready manuscript version and can compare hybrid retrieval with or without cross-encoder reranking. |
| AI Experiment Lab | `GET /api/developer/datasets`, `GET /api/developer/experiment-configs`, `POST/GET /api/developer/experiments`, detail/failures endpoints | Runs diagnostic smoke/development Hybrid-vs-reranker comparisons through memory-isolated background subprocess phases. |
| Liveness/readiness | `GET /health/live`, `GET /health/ready` | Infrastructure only; not used as product data. |

## Ingestion cancellation verification (2026-08-30)

New uploads are accepted only after storage and queue publication succeed; then
older queued/running ingestion jobs in that project are cancelled. Failed uploads
do not cancel the previous job. Project locks serialize acceptance, cancellation,
and promotion; workers reject superseded retries and late completion. Cancelling
retains the original file and any already-written, version-scoped derived data.
No cancelled version becomes current, and cancelled work is not resumed if its
replacement fails. Entity extraction checks cancellation before each chunk and
before persisting mentions. An in-flight inference/embedding/index operation may
finish; this is cooperative cancellation, not termination of a provider process.
Cancelled jobs retain stage timings, completion time, and safe `USER_CANCELLED`
or `SUPERSEDED` reasons. A worker restart is required when upgrading old workers.

Verified through the real in-app browser, with no application API interception:
create a disposable project, upload a GLiNER baseline, upload a 30-chapter Gemma
version, reload, click Cancel processing, then upload another Gemma version and
replace it with a GLiNER upload. The manual cancellation retained the baseline;
the replacement cancelled its predecessor and became current only after success.
Job IDs: baseline `31c5029f-ad7f-417a-a47e-5af689ff1de6`, manual cancellation
`804f63c6-22f0-4ce5-8b77-1a61bbf9ac76`, automatic cancellation
`d1babaa9-d6b2-447f-9c1e-213745268f9c`, replacement
`77f376d5-e143-48f4-abb8-09b14c9abe72`. No partial entity mentions were published
for the manually cancelled version. The disposable project was removed after
verification. Existing Alice v6 was cancelled as superseded on worker redelivery;
Alice v7 remained current.

Checks: 14 targeted backend/API/queue tests passed; backend unit discovery passed
44 tests with 24 database tests skipped in that invocation; all 11 frontend tests
passed; TypeScript, targeted ESLint, production Docker builds and local service
startup passed. No prompt/model behavior changed, so no AI promotion experiment
was run. Lesson 5.2 progress and learning artifacts were not advanced.

## Existing response gaps

`ProjectRead` now includes the current manuscript version label and chapter
count. The following later-course aggregates remain absent:

- character count;
- continuity issue count;
- last analyzed time;
- analysis status.

The UI renders an em dash for absent aggregates instead of converting missing
data to zero. A backend/config endpoint for supported manuscript languages is
also absent, so the forms accept a BCP 47 code and default to the backend default
`en`.

## Missing core work and deferred capabilities

These are implementation gaps, not features delivered by the course revision.
`COURSE.md` owns scope and lesson order. Keep deferred UI paths explicitly
unavailable/disabled. Reuse existing structured facts and embedded evidence;
a placeholder or proposed endpoint does not require a new subsystem.

| Area | Existing gap / proposed contract | Course disposition |
| --- | --- | --- |
| Dashboard | Aggregate summary and recent activity endpoints are absent. | Deferred rich dashboard; keep existing supported summaries and navigation. |
| Delete old version | No endpoint specified; delete control is disabled. | Deferred advanced version management; core 10.1 verifies replacement/failure correctness. |
| Chapter issue badges | Continuity issue contracts are absent. Structured-memory evidence already supports exact source-range navigation; continuity links still need wiring. | Core 9.1 wires issue evidence; badges are polish only if useful. |
| Character attributes | Separate structured facts are real; a dedicated attribute contract is absent. | Core 9.1 reuses facts and manuscript evidence; a second extraction/attribute API is not required. |
| Chat streaming | `POST /api/projects/{project_id}/chat/stream` is absent. | Core 7.1: shared Ask/contextual-panel backend with SSE, grounding, scope, and abstention; manuscript-backed QA does not require completed structured memory. |
| Chat history | Thread list/detail endpoints are absent. | Core QA conversation persistence; reuse the shared backend, not separate panel history infrastructure. |
| Start continuity | `POST /api/projects/{project_id}/analysis/continuity` is absent. | Core 9.1: one character-attribute family first, using existing facts and both manuscript passages. |
| Issues | Issue list/detail endpoints are absent. | Core 9.1: possible issues with two evidence passages. Other issue categories are deferred. |
| Issue feedback | `POST /api/projects/{project_id}/issues/{issue_id}/feedback` is absent. | Core 9.1: writer verdict, reason, and optional note, in the first usable issue-review slice. |
| Check new text | `POST /api/projects/{project_id}/check-text` is absent. | Deferred; not a core completion blocker. |
| Analysis | Continuity analysis list/detail endpoints are absent. | Core 9.1: scoped run status/results and version-aware history; no elaborate activity dashboard. |
| Evidence lookup | No standalone endpoint specified. | Core evidence arrives embedded in facts/events/issues/chat citations; reuse that contract and manuscript navigation. |
| Product-help chat | No core backend workflow is implemented. | Deferred; do not add help routing or another retrieval corpus to finish QA. |

Planning/tool selection in 7.2 and QA/agent evaluation in 8.1 extend the same QA
and Experiment Lab paths, including decision failures and category regressions.
No separate agent console or monitoring dashboard is required. Rewriting/HyDE
are optional labs, not missing core APIs. Post-core 12.1 LoRA training/evaluation
is an isolated script or notebook using existing experiment conventions; there
is no training API, editor-profile UI, or adapter integration requirement.
Cloud deployment and AI CI/CD/GTM are outside the course.
Preserve current model choices and historical verification results below.

## Developer experiment boundaries

Manuscript upload independently exposes three entity extractors. Gemma remains
the default; GLiNER2.5 Base is an explicit fast development option and Qwen3.5
9B an alternative LLM. The public catalog contains only stable IDs and display
text, never provider URLs or credentials. Unknown choices are rejected before
storage. GLiNER uses the pinned CPU boundary model directly; LLMs use their
dedicated LiteLLM aliases with the unchanged V2 prompt. There is no automatic
fallback. Resolution is a separate explicit action. The extractor selection is immutable for a version and
shown in version history; re-upload to choose another model.

New ingestion jobs record elapsed wall time for parsing, embedding, indexing
and entity extraction. Durations accumulate across retries; active-stage time
is returned separately. Old jobs have no retrospective stage measurements.

Verified on 2026-08-30 with three real browser uploads through Docker, without
application API interception. For the same tiny manuscript, the recorded
`entity_extraction` stage took GLiNER 285 ms, Gemma 76076 ms, and Qwen9B 8892 ms.
These include runtime overhead and possible model loading; they are smoke
measurements, not a full-manuscript benchmark or quality comparison. Test
projects were deleted; the existing Alice version and its 1243 mentions were
preserved. The database is at migration `20260830_08`.

Verification: backend 51 passed / 1 skipped against PostgreSQL in the updated
image; frontend 6 unit tests, 5 mocked browser tests and 3 real browser tests
passed; lint, TypeScript and the production frontend build passed. The pinned
24-case GLiNER eval retained precision 0.7368, recall 0.7778 and F1 0.7568, with
no invalid spans. No new LangSmith trace IDs were recorded. The ordinary
Compose build was blocked fetching base-image metadata; deployment instead
used offline code overlays on the existing same-dependency images. A clean
base-image rebuild remains unverified. No course progress or learning note was
advanced by this integration; the developer's full-manuscript UI check remains
to be done.

### Entity resolution boundaries (Lesson 5.2)

The resolver uses the server-owned `storyguard-entity-resolution` alias, mapped
to local `gemma4:e4b`, regardless of the upload extractor. It accepts only
`merge`, `keep_separate`, or `needs_review` and server-issued evidence IDs.
One invalid-output repair is allowed, then the candidate is marked as a technical
failure, not as an LLM `needs_review` decision.
`config/models.yaml` now defaults to `auto_apply: true`, explicitly requested
by the developer after the initial review-only diagnostic. This server-wide
setting applies eligible decisions in the same transaction that saves each
model prediction, before the next comparison. Saved eligible recommendations
from older runs are also applied at startup/resume, before new inference;
it does not start jobs on upload or apply existing results just by refreshing
the page. `false` remains an optional review-only configuration. The UI labels
the mode as **Automatic merging: ON/OFF** and explains the remaining review
cases. Applied pairs leave the pending list, the applied count increments, and
character/detail queries refresh while the job is running. Unapplied suggestions
are explicitly labeled "not applied"; conflicting decisions are labeled blocked.
No model, prompt, evidence validation, or conflict guard was changed;
the initial diagnostic's false merge remains a known quality risk. Enabling
application does not repair model-call failures. The existing Experiment Lab UI is unchanged;
`backend/scripts/entity_resolution_experiment.py` runs the frozen diagnostic.

Candidate generation is deliberately bounded: same-type lexical/local pairs,
at most 2,000 per version. Each batch starts at most 20 Gemma pair attempts and
stops starting new comparisons after 300 seconds. Eligible remaining work is
automatically queued under the same job ID; batch boundaries never mark it
completed or require a user click. An already-started pair may finish
after that batch budget: it has a configurable 180-second deadline per model
request (including a separate repair request), and a 360-second pair ceiling.
The HTTP client and resolution-only LiteLLM deployment use the same 180-second
request timeout; keep `config/models.yaml` and `config/litellm.yaml` aligned
when tuning it. No prompt, model, output-token limit, or evidence rule changed.
The UI exposes remaining work and
the candidate ceiling. Distant aliases may never become candidates. Each model
call receives up to two source windows, not the entire manuscript; the drawer
shows those windows, not a claim of exhaustive evidence. Character detail
currently shows up to 20 distinct mention windows.

Project/current-ready-version checks and source-offset revalidation apply to
both model persistence and manual decisions. Inference holds no database locks.
Duplicate deliveries and repeated decisions are idempotent. A saved human
decision wins over an in-flight model result. A failed model comparison does not
abort other pairs. Timeout/connection/429/5xx failures receive one deferred retry
after untouched pairs. The saved attempt count enforces at most two attempts
across all batches and Stop/Resume, including legacy `MODEL_UNAVAILABLE` rows
with an available attempt count. Legacy rows without counters acquire the same
persistent cap when processed.
`remaining` counts only comparisons still eligible for automatic work.
Resume does not reset this cap or repeat genuine model decisions or manual
overrides. Exhausted technical failures remain errors,
not invented review decisions. Schema/invalid-evidence failures and other 4xx
responses are not automatically retried beyond the existing output repair.
Queue, database, or manuscript-scope failures can still stop the job, never the
already-ready manuscript. Applied keep-separate
constraints block contradictory merge chains. Append-only audit snapshots
preserve evidence and before/after canonical links; an undo UI, cross-version
identity migration, attribute conflict analysis, and semantic alias retrieval
are not implemented.

Immediate application is order-sensitive: a later separation can conflict with
merges already committed. Such a decision is flagged `CLUSTER_CONFLICT`; it does
not silently undo earlier merges. Existing saved batches are checked together
by the same conflict guard. This application-timing change was explicitly
requested; it is not a claim of improved model accuracy.

Cancellation reuses the existing cancelled job state. The worker checks it
during inference (once a second), before persistence, and before automatic
application. The run-attempt counter fences late results from an earlier run;
queued-stage timestamps also fence late enqueue failures after Stop/Resume.
Cancellation closes the local wait/request but does not promise to terminate
generation already accepted by Ollama. No provider process or unrelated job is
stopped. Stop does not undo completed merges. An active request's late result
is discarded; older unapplied recommendations remain available on Resume.

Migration `20260830_11` retains a separate append-only model audit row for each
attempt and permits a null decision on failed requests. Historical audit rows
are preserved. Human/automatic applications remain unique per candidate/source.
Progress distinguishes successful decisions, technical failures, review cases,
and applied decisions; "processed" includes failed comparisons, not just successes.

#### Immediate application verification (2026-08-31)

The developer explicitly requested that a `merge` decision be merged immediately.
The worker now calls the existing automatic-application helper within the same
transaction as each saved prediction and at startup/resume for older pending
recommendations. The UI invalidates character, Story Bible, and entity-detail
queries when the applied count changes during a running job. Unapplied
recommendations are no longer labeled ambiguously as "Model: merge".

Changed files: `backend/app/queue/tasks/entity_resolution.py`,
`backend/tests/test_entity_resolution.py`,
`frontend/components/entity-resolution.tsx`,
`frontend/components/entity-resolution.test.tsx`, and this integration report.
The feature workflow reused existing application and conflict checks; no new
schema, model, prompt, evidence rule, dependency, or course artifact was added.

Backend: 80 tests, 78 passed, 2 optional tests skipped. Regression checks observe
a committed merge through a separate API session before the next comparison,
then verify it survives Stop or an unexpected later job failure. Another check
verifies a later contradictory separation stays blocked without undoing earlier
merges. Existing isolation, review-only mode, audit/idempotency, retries and
late-response cancellation tests still pass. Frontend: 14 tests passed, including
character/detail refresh while running; lint, TypeScript, Docker builds and
`git diff --check` passed.
The real browser-to-storage/worker smoke also passed against the deployed
changes in 48.5 seconds: GLiNER upload, Gemma resolution, Stop/reload/Resume,
automatic merge and source evidence, without intercepting application APIs.
The disposable story was removed by test cleanup. All local services are up;
backend and model-gateway health checks pass.

Deployment waited for Alice's active batch to finish naturally. Its screenshot
Dodo candidate `001c52a9-1042-45d4-aae5-400d1a11c6fa` already had an automatic
merge audit at `2026-08-31T08:06:13.332925Z`; the model recommendation was saved
at `07:59:12.730262Z`. This confirms the previous delay and actual application.
No manual Dodo override or extra Alice resolution job was started for this fix.
The batch/candidate limits remain unchanged. Model-quality evaluation was not
rerun, and Lesson 5.2/checkpoint/learning-note status remains unchanged.

#### Reliability verification (2026-08-31)

Approved feature work changed the resolution worker/API/schema/domain modules,
`app/ai/entity_resolution.py`, the optional request timeout in the shared
`app/ai/entity_extraction.py` client, `db/models/entity_resolution.py`, migration
`20260830_11_resolution_retries.py`, both model configuration files, the Story
Bible resolution component, and its backend/frontend/E2E tests. No dependency,
prompt, model, candidate-generation, evidence-validation, or merge-conflict-rule
change was made. The feature workflow kept this separate from course advancement;
Postgres guidance informed short transactions and the retained attempt audit.

Verification:

- Full backend suite: 77 tests, 75 passed and 2 skipped. The skipped 61-second
  regression ran separately and passed (the focused suite passed 19/19 before
  the last two fast regression cases were added). The other skip is the optional
  Elasticsearch integration test, outside this change.
- The slow regression lets a pair run for 61 seconds even with a one-second
  start-new-work budget; it succeeds and the next pair remains pending.
- Tests cover timeout/connection/429/5xx continuation and deferred retry,
  invalid-output isolation, append-only retry history, legacy failure recovery,
  manual-decision preservation, Stop/Resume including late model results and
  late enqueue failure, and project/version isolation. Provider-body privacy
  assertions passed.
- Frontend: 13 tests passed; ESLint, TypeScript, production build, and
  `git diff --check` passed.
- Real Playwright test passed in about 1.1 minutes without mocked application
  APIs: create disposable story, upload with GLiNER, start Gemma resolution,
  Stop during inference, reload, Resume, verify one automatic evidence-backed
  merge and an unchanged ready manuscript. The disposable project was deleted
  by test cleanup; Alice was neither rerun nor manually modified.
- Smoke resolution job: `827977fb-6ee5-4573-9608-ea2729dcb670`.
  Cancelled trace: `01a054d9-4b3f-7940-ab0f-bf7025927c26` (1.003 seconds).
  Resumed merge trace: `01a054d9-4cbc-7fb2-9129-79118e21c407` (53.167 seconds).
- Backend, worker, and frontend Docker builds passed. Migration `20260830_11`
  applied; `alembic check` reports no new operations (the existing cyclic-FK
  warning remains). Local services were updated; the gateway was restarted to
  load its resolution-specific timeout. No active user jobs were interrupted.

This is a reliability smoke, not a model-quality experiment or promotion.
The previous frozen quality evaluation and its known false merge remain
unchanged. Candidate coverage still caps at 2,000, each batch remains bounded,
and Ollama may finish an already-submitted request after Stop. The developer
checkpoint is to reload Alice's Story Bible, start/resume resolution, Stop,
then Resume and observe preserved progress. At final verification Alice's
current ready version was v9, with no resolution job yet, so its first action
is **Resolve entities**. The older v7 human audit still contains two merges and
one keep-separate decision. The checkpoint has not yet been reported; no learning note or
course progress was changed by this fix (Lesson 5.2 remains in progress).

#### Initial Lesson 5.2 verification

Ordinary Docker image builds and the additive `20260830_09` migration succeed.
`alembic check` detects no model/migration drift (it still warns about the
pre-existing projects/manuscript_versions FK cycle). Backend verification:
61 passed, 1 Elasticsearch test skipped; frontend: 8 unit tests, lint and
TypeScript passed. The developer checkpoint and learning note remain pending;
Lesson 5.2 has not been marked complete.

The initial review-only in-app browser smoke passed without application API interception:
create a disposable story → upload through GLiNER → run Gemma resolution →
inspect the source drawer → manually merge Nora Vale/Nori → see one character
with both aliases. The model recommendation remained unapplied until the click;
the manuscript remained ready. Job/decision rows recorded separate model and
human audit events; the model trace ID was
`01a05458-7f40-7c02-9a35-36716cd86112`. The synthetic project, original upload and
index documents were removed afterward. All 3,753 pre-existing Alice mentions
remain present with no resolution links applied. A reusable Playwright smoke
test now expects automatic application, but the initial browser verification used the in-app
browser directly, not that test runner.

After enabling the default, verification passed: 63 backend tests plus one
skipped Elasticsearch test, 9 frontend unit tests, lint, TypeScript and the
production Docker build. Database tests exercise automatic merge/separation,
review/error exclusion, conflicting chains, human overrides, audit persistence,
and duplicate delivery. The live API reports `auto_apply: true`. Only the
frontend container was replaced; the active ingestion worker was not restarted
and no user manuscript resolution job was started. This is an application-policy
change, not a new model-quality evaluation; the frozen diagnostic
`entity-resolution-v1-test-1d847fca` and its original configuration are preserved.
No new model-evaluation or LangSmith trace IDs were generated for this change.
Course progress, the developer checkpoint, and the learning note are unchanged.

The Experiment Lab exposes only server-known Gacha smoke/development suites and
the controlled Hybrid RRF versus Hybrid RRF + cross-encoder pair. These UI runs
are diagnostic-only. The 233-query held-out promotion evaluation remains in the
restartable CLI shard workflow so the MacBook never accumulates both models in
a long-lived application worker.

The frontend does not expose arbitrary story selection, raw model IDs, or a
candidate-promotion endpoint. Uploaded manuscripts are not scored because they
do not have query/evidence ground truth. Safe LangSmith identifiers may be
included when available, but private traces, prompts, or credentials are never
returned.

## Expected error semantics

When these APIs are added, use the standard safe error envelope and stable codes
such as `AI_PROVIDER_UNAVAILABLE`, `RETRIEVAL_UNAVAILABLE`, `ANALYSIS_FAILED`,
and `INSUFFICIENT_EVIDENCE`. Insufficient evidence is an answer state, not a
technical failure. Job responses must supply real status, stage, completed,
total, and safe error fields.
