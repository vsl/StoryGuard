# Frontend / Backend API Gap Matrix

Snapshot: 2026-08-24 after Lesson 3.1A integration.

The frontend is wired to the contracts in the backend and UI specifications.
This document records what the repository actually publishes today. “Missing”
means the UI displays an explicit unavailable state; it does not imply a hidden
mock implementation.

## Available now

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
| Job progress | `GET /api/jobs/{job_id}` | Upload UI polls state, safe errors, current-stage elapsed time, and accumulated per-stage durations. |
| Parsed chapters | `GET /api/projects/{project_id}/chapters`, `GET /api/projects/{project_id}/chapters/{chapter_id}` | Read-only chapter list and text use the project's current ready version. |
| Direct search | `GET /api/projects/{project_id}/search?q=...&rerank=...` | Project search uses the current ready manuscript version and can compare hybrid retrieval with or without cross-encoder reranking. |
| AI Experiment Lab | `GET /api/developer/datasets`, `GET /api/developer/experiment-configs`, `POST/GET /api/developer/experiments`, detail/failures endpoints | Runs diagnostic smoke/development Hybrid-vs-reranker comparisons through memory-isolated background subprocess phases. |
| Liveness/readiness | `GET /health/live`, `GET /health/ready` | Infrastructure only; not used as product data. |

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

## Missing product endpoints

| Area | Required endpoint or contract | Blocked behavior |
| --- | --- | --- |
| Dashboard | Aggregate summary and recent activity contract | Complete counts, continuity health, and recent activity. |
| Delete old version | No endpoint specified yet | The v1 delete control remains disabled. |
| Chapter issue badges and evidence anchors | Later continuity/evidence contracts | Chapter text is real now; issue counts and exact evidence spans remain future work. |
| Characters | `GET /api/projects/{project_id}/characters` | Character list. |
| Character detail | `GET /api/projects/{project_id}/characters/{entity_id}` | Attributes, facts, and evidence. |
| Locations | `GET /api/projects/{project_id}/locations` | Location list. A separate detail contract is not currently specified. |
| Objects | No endpoint specified yet | Objects tab. |
| Facts | `GET /api/projects/{project_id}/facts` | Fact list/filter data and evidence. |
| Events/timeline | `GET /api/projects/{project_id}/events` | Events and chronological/narrative timeline. |
| Relationships | `GET /api/projects/{project_id}/relationships` | Relationships tab. |
| Entity candidates | `GET /api/projects/{project_id}/entity-resolution/candidates` | Duplicate candidate cards. |
| Entity decision | `POST /api/projects/{project_id}/entity-resolution/{candidate_id}/resolve` | Merge/keep-separate decisions. |
| Chat streaming | `POST /api/projects/{project_id}/chat/stream` | Full Ask workspace and contextual side panel. |
| Chat history | Thread list/detail endpoints | Persisted conversation history. |
| Start continuity | `POST /api/projects/{project_id}/analysis/continuity` | Run-analysis action. |
| Issues | Issue list/detail endpoints | Filters, issue cards, and evidence comparison. |
| Issue feedback | `POST /api/projects/{project_id}/issues/{issue_id}/feedback` | Valid/not-an-issue verdicts, reason, and note. |
| Check new text | `POST /api/projects/{project_id}/check-text` | Passage consistency result. |
| Analysis | Analysis list/detail endpoints | Latest run, metrics, version metadata, and history. |
| Evidence lookup | No standalone endpoint specified | Evidence must arrive embedded with facts, issues, events, or chat citations. |

## Developer experiment boundaries

Manuscript upload independently exposes three entity extractors. Gemma remains
the default; GLiNER2.5 Base is an explicit fast development option and Qwen3.5
9B an alternative LLM. The public catalog contains only stable IDs and display
text, never provider URLs or credentials. Unknown choices are rejected before
storage. GLiNER uses the pinned CPU boundary model directly; LLMs use their
dedicated LiteLLM aliases with the unchanged V2 prompt. There is no automatic
fallback or entity resolution. The selection is immutable for a version and
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
