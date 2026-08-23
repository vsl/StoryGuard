# Frontend / Backend API Gap Matrix

Snapshot: 2026-08-23.

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
| Liveness/readiness | `GET /health/live`, `GET /health/ready` | Infrastructure only; not used as product data. |

## Existing response gaps

`ProjectRead` does not currently include the following fields needed by project
cards and overview metrics:

- current manuscript version label/number;
- chapter count;
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
| Manuscript upload | `POST /api/projects/{project_id}/manuscripts` | Upload and processing job creation. |
| Versions | `GET /api/projects/{project_id}/manuscripts` | Version history. |
| Version detail | `GET /api/projects/{project_id}/manuscripts/{version_id}` | Version metadata. |
| Delete old version | No endpoint specified yet | The v1 delete control remains disabled. |
| Chapters | `GET /api/projects/{project_id}/chapters` | Chapter list and issue badges. |
| Chapter detail | `GET /api/projects/{project_id}/chapters/{chapter_id}` | Read-only manuscript, paragraph anchors, and deep-link highlighting. |
| Characters | `GET /api/projects/{project_id}/characters` | Character list. |
| Character detail | `GET /api/projects/{project_id}/characters/{entity_id}` | Attributes, facts, and evidence. |
| Locations | `GET /api/projects/{project_id}/locations` | Location list. A separate detail contract is not currently specified. |
| Objects | No endpoint specified yet | Objects tab. |
| Facts | `GET /api/projects/{project_id}/facts` | Fact list/filter data and evidence. |
| Events/timeline | `GET /api/projects/{project_id}/events` | Events and chronological/narrative timeline. |
| Relationships | `GET /api/projects/{project_id}/relationships` | Relationships tab. |
| Entity candidates | `GET /api/projects/{project_id}/entity-resolution/candidates` | Duplicate candidate cards. |
| Entity decision | `POST /api/projects/{project_id}/entity-resolution/{candidate_id}/resolve` | Merge/keep-separate decisions. |
| Direct search | `GET /api/projects/{project_id}/search?q=...` | Grouped project search. |
| Chat streaming | `POST /api/projects/{project_id}/chat/stream` | Full Ask workspace and contextual side panel. |
| Chat history | Thread list/detail endpoints | Persisted conversation history. |
| Start continuity | `POST /api/projects/{project_id}/analysis/continuity` | Run-analysis action. |
| Issues | Issue list/detail endpoints | Filters, issue cards, and evidence comparison. |
| Issue feedback | `POST /api/projects/{project_id}/issues/{issue_id}/feedback` | Valid/not-an-issue verdicts, reason, and note. |
| Check new text | `POST /api/projects/{project_id}/check-text` | Passage consistency result. |
| Analysis | Analysis list/detail endpoints | Latest run, metrics, version metadata, and history. |
| Job progress | `GET /api/jobs/{job_id}` | Real queued/running/completed/failed progress. |
| Evidence lookup | No standalone endpoint specified | Evidence must arrive embedded with facts, issues, events, or chat citations. |

## Missing developer endpoints

| Capability | Endpoint |
| --- | --- |
| Dataset catalog | `GET /api/developer/datasets` |
| Controlled configuration catalog | `GET /api/developer/experiment-configs` |
| Start experiment | `POST /api/developer/experiments` |
| Experiment history | `GET /api/developer/experiments` |
| Experiment detail | `GET /api/developer/experiments/{experiment_id}` |
| Failure browser | `GET /api/developer/experiments/{experiment_id}/failures` |

The frontend does not expose an arbitrary model-ID field and does not provide a
candidate-promotion endpoint. Safe LangSmith run/trace IDs may be included in
future experiment and chat metadata, but private traces, prompts, or credentials
must never be returned.

## Expected error semantics

When these APIs are added, use the standard safe error envelope and stable codes
such as `AI_PROVIDER_UNAVAILABLE`, `RETRIEVAL_UNAVAILABLE`, `ANALYSIS_FAILED`,
and `INSUFFICIENT_EVIDENCE`. Insufficient evidence is an answer state, not a
technical failure. Job responses must supply real status, stage, completed,
total, and safe error fields.
