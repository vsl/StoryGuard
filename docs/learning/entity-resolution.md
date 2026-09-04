# Entity Resolution

## Mental model

```text
EntityMention pairs
  -> deterministic candidate generation
  -> cached xCoRe groups
       -> exact aligned same-group link: merge shortcut
       -> no link: Gemma comparison
  -> merge | keep_separate | needs_review
  -> evidence/conflict validation
  -> prediction + canonical identity commit
  -> append-only decision audit
```

Entity resolution answers whether two manuscript mentions refer to the same
story entity. A candidate pair is only a comparison opportunity, not evidence
that the mentions match. xCoRe group membership is a routing signal, not a
calibrated confidence score. Gemma may decide `merge`, `keep_separate`, or
`needs_review`, but StoryGuard accepts a non-review decision only with
server-issued evidence covering both mentions.

## StoryGuard request and data flow

`POST /api/projects/{project_id}/entity-resolution/run` creates or resumes one
version-scoped `JobRun`. Taskiq dispatches
`backend/app/queue/tasks/entity_resolution.py`, which prepares the bounded
candidate set through `backend/app/entity_resolution.py`.

Each previously unseen mention receives an identity anchor (`Entity`) and its
original surface form (`EntityAlias`). Candidate generation compares only the
six supported categories: characters/people, facilities/buildings,
countries/settlements, natural/geographical locations, organizations, and
vehicles. General artifacts and catch-all entities are deliberately excluded.
Candidate discovery is capped at 2,000 pairs per manuscript version; completion
therefore means no eligible pair remains inside the discovered set, not that
the entire book contains no unresolved duplicate.

For the promoted `coreference_gemma` pipeline, `backend/app/ai/coreference.py`
runs the pinned coreference model in an isolated Python 3.11 subprocess. The
cache key includes the version, content, model/runner and dependency identity.
The cache stores source offsets, hashes and groups rather than manuscript text.
An exact aligned same-group link can bypass Gemma and apply `merge`; all other
candidates go to `backend/app/ai/entity_resolution.py`, where Gemma returns
validated structured output with at most one repair.

Automatic decisions are applied transactionally. Canonical links and the
prediction commit together, while `ResolutionDecision` keeps an append-only
audit containing before/after state, evidence and safe model provenance. Stop
preserves committed decisions and fences late results. The same job automatically
requeues bounded worker batches until no eligible discovered candidates remain;
Resume increments the attempt fence without repeating saved decisions.

The production UI/API path is
`backend/app/api/entity_resolution.py` ->
`frontend/components/entity-resolution.tsx` ->
`frontend/components/core-screens.tsx`. Applied pairs leave the review list,
entity queries refresh, original canonical surface forms remain in the database
audit, and API responses omit aliases equal to the canonical name. On desktop,
the Story Bible list and detail workspace scroll independently.

## Evidence, safety and failure behavior

- Project and manuscript-version scope is enforced in every API and worker
  transaction, not delegated to prompts or browser state.
- Pair evidence is rebuilt from stored mention offsets before inference and
  checked again before persistence.
- A merge cannot cross a saved `keep_separate` constraint; conflicting chains
  become reviewable conflicts instead of silently corrupting identities.
- Invalid JSON/evidence gets one repair. Repeated invalid output, timeouts,
  connection failures, rate limits and server failures affect only that pair;
  other comparisons continue. Temporary failures have one later retry.
- Each Gemma request has a 180-second deadline; a pair may outlive the
  five-minute start-new-work batch budget. Stop discards its late result.
- Coreference failure or its separate 30-minute ceiling falls back visibly to
  Gemma. An unfinished scan is killed; a completed version/content cache can be
  reused after Resume.
- Trace/export failure never blocks database commits. The database decision
  audit remains the source of truth.

The main semantic risk is a wrong xCoRe group: a shortcut can apply an incorrect
merge without Gemma review. Exact evidence proves provenance, not identity
correctness. The promoted diagnostic actually observed this failure on two
unrelated Alex mentions.

## Experiment and trade-off

The frozen five-case diagnostic `coreference-gemma-528d5bc2335d` compared pure
Gemma with xCoRe + Gemma:

| Metric | Gemma | xCoRe + Gemma |
| --- | ---: | ---: |
| LLM calls including repairs | 5 | 4 |
| Decision accuracy | 80% | 60% |
| Merge precision | 66.7% | 50% |
| Incorrect merges | 1 | 2 |
| Review rate | 20% | 0% |
| Gemma wall time | 74.967 s | 53.350 s |

Coreference added 1.719 seconds after loading, producing about 55.068 seconds
excluding startup: roughly 27% faster in this tiny run. The first
download/startup raised the candidate total to 391.375 seconds. Local API cost
was $0, but compute and latency are not free. The developer promoted the faster
pipeline while explicitly accepting its measured quality risk. This is not a
full-book benchmark, and Qwen comparison remains deferred.

## LangSmith observability

Each worker invocation creates an `entity_resolution_batch` root. Children are
lightweight `resolution_coreference` stages and individual Gemma
`entity_resolution` calls. Fresh subprocess scans are linked with
`source_scan_trace_id`; a cache-hit child represents reuse, not new inference.

Batch outputs separate work attempted in this invocation from cumulative
`version_totals`. `merge_decisions_applied: 2` therefore meant two committed
merges observed for the version, not two merges made by the selected batch. In
the checkpoint trace sequence:

- Batch 1 (`01a0589d-9ce3-75c2-936e-981d3e5a2559`) applied one xCoRe shortcut,
  then ended `user_stopped`.
- Batch 2 (`01a0589d-d1cc-7763-aad6-aab30b201ef2`) reused the coreference cache,
  applied no xCoRe shortcut in that batch, called Gemma once, and completed with
  two cumulative applied merges.

The developer correctly distinguished model/resolver provenance from manuscript
evidence: `model: sapienzanlp/xcore-litbank` identifies the coreference stage,
`resolver: gemma` identifies a particular pair comparison, while a chapter is
the source of evidence rather than the decision-maker.

## Stored data and trace data

```text
manuscript chapters/chunks (PostgreSQL)
  -> EntityMention: exact text span
  -> Entity / EntityAlias: current identity view
  -> ResolutionCandidate: pair waiting for or carrying a result
  -> ResolutionDecision: append-only decision audit
  -> JobRun: progress and lifecycle

LangSmith (observability, not a second source of truth)
  -> entity_resolution_batch: one worker batch summary
  -> resolution_coreference: xCoRe cache/scan stage
  -> entity_resolution: one Gemma pair comparison
```

PostgreSQL is the source of truth. LangSmith is an execution record: it helps
diagnose routing, latency, failures and model use, but a trace cannot replace
the database audit. There is no separate LangSmith-trace table. Relevant trace
IDs are retained in a candidate's safe `model_metadata` and decision audit.

### PostgreSQL: manuscript evidence and identity

The original manuscript text is stored in the version's chapters and chunks.
Entity resolution stores positions into that text rather than treating model
text as evidence.

| Table / field | Meaning |
| --- | --- |
| `entity_mentions.id` | ID of one exact mention in the manuscript. |
| `entity_mentions.entity_id` | Its current identity anchor; following `merged_into_id` reaches the effective canonical entity. |
| `manuscript_version_id`, `chapter_id`, `scene_id`, `chunk_id` | Server-enforced manuscript location and scope. `scene_id` is optional. |
| `entity_type` | Supported type: character/person, facility/building, country/settlement, geographical location, organization or vehicle. |
| `surface_text` | Exact words found in the manuscript, for example `Daniel Cross`. |
| `start_offset`, `end_offset` | Half-open character positions in the chapter. They rebuild evidence directly from stored text. |
| `prompt_version`, `model_alias` | Provenance of the earlier entity-extraction step. |
| `entities.canonical_name` | Current displayed/main name for an identity. |
| `entities.status` | `active`, `merged`, or `needs_review`. |
| `entities.merged_into_id` | ID of the surviving canonical entity after a merge; empty for a root entity. |
| `entity_aliases.alias` | Another original surface form of an entity. |
| `entity_aliases.normalized_alias` | Normalized form used for matching/searching. |

An alias equal to `canonical_name` remains in the database for audit and
reversal, but the API hides that redundant alias in the Story Bible UI.

### PostgreSQL: candidates, decisions and jobs

| Table / field | Meaning |
| --- | --- |
| `entity_resolution_candidates.left_mention_id`, `right_mention_id` | The two mentions being compared. A candidate is an opportunity to compare, not a confirmed duplicate. |
| `llm_decision` | The latest accepted model recommendation: `merge`, `keep_separate`, or `needs_review`. |
| `applied_decision` | A committed identity decision: only `merge` or `keep_separate`. Empty means no decision was applied. |
| `error_code` | Safe technical failure/conflict code, such as invalid model output or timeout; it is not a model decision. |
| `evidence_ids` | IDs of server-issued evidence supplied to and accepted for the comparison. |
| `model_metadata` | Safe model, routing, latency and trace provenance described below. |
| `entity_resolution_decisions.decision` | A saved `merge` or `keep_separate` audit event. |
| `source` | Who created this event: `model`, `automatic`, or `human`. A model recommendation and its automatic database commit are separate audit events. |
| `attempt` | Attempt number for that saved decision. |
| `evidence` | The server-issued evidence snapshot used for the decision. |
| `before`, `after` | Identity state immediately before and after an application, allowing the change to be audited. |
| `job_runs.status` | Lifecycle: `queued`, `running`, `completed`, `failed`, or `cancelled`. |
| `job_runs.stage` | The current worker stage shown to the UI. |
| `completed_units`, `total_units` | Progress counters for the job. |
| `attempts` | Job/batch fencing and retry count; it is not the number of Gemma calls. |
| `idempotency_key` | Prevents accidental duplicate job creation. |
| `error_code`, `error_message_safe` | Safe job error shown to the UI; raw provider/database errors are not exposed. |
| `stage_durations_ms` | Timing per job stage. |

`model_metadata` on a candidate can include `prompt_version`, `prompt_hash`,
`model_alias`, `configured_model`, `model_digest`, `resolved_model`,
`latency_ms`, `repair_count`, token `usage`, `trace_id`, `error_code`,
`job_id`, `batch_trace_id`, `pair_attempt`, `resolver`, `pipeline`, and
`request_timeout_seconds`. `trace_id` identifies the individual comparison;
`batch_trace_id` identifies its parent worker batch.

### LangSmith: root batch trace

One Taskiq worker invocation produces `entity_resolution_batch`. Its input is
only `job_id`. Its metadata adds `batch_number`, `project_id`,
`manuscript_version_id`, `pipeline`, `auto_apply`, `max_gemma_attempts`, and
`batch_budget_seconds`.

Its output fields mean:

| Field | Meaning |
| --- | --- |
| `outcome` | How this invocation ended: for example `completed`, `continuing`, `stopped`, or `completed_with_errors`. It does not prove the whole book is duplicate-free. |
| `end_reason` | Concrete stopping reason, such as `no_eligible_pairs`, `time_budget`, `pending_work`, or `user_stopped`. |
| `gemma_attempts` | Number of Gemma requests made in this batch. |
| `coreference_shortcuts` | Number of candidates routed through an exact xCoRe-group merge shortcut in this batch. |
| `retry_attempts`, `failed_attempts` | Retry and failed-comparison counts for this invocation. |
| `continuation_queued` | Whether another bounded worker batch was queued automatically. |
| `duration_ms` | Wall-clock duration of the worker batch. |
| `coreference_cache_hit` | Whether the xCoRe document result was reused rather than recomputed. |
| `coreference_scan_trace_id` | Trace ID of the original xCoRe scan that produced the reused result. |
| `version_totals` | Latest cumulative counts across this manuscript version, not changes made only by this batch. |

`version_totals` contains `remaining`, `review_count`, `error_count`,
`successful_count`, `applied_count`, `coreference_merge_count`,
`gemma_comparison_count`, `merge_decisions_applied`, and
`separate_decisions_applied`. Thus a batch with `gemma_attempts: 1` and
`merge_decisions_applied: 2` may have made only one new merge while reporting
two total applied merges for the version.

### LangSmith: model-stage traces

`resolution_coreference` receives only `manuscript_version_id`,
`document_count`, and aggregate `text_chars`. It reports `outcome`,
`cache_hit`, a hash-like `cache_key`, xCoRe `model` and `revision`,
`source_scan_trace_id`, `source_scan_load_ms`, and `source_scan_wall_ms`.
`cache_hit: true` means the chapter/window groups were read from the local cache;
it does not mean that xCoRe made a decision about a particular candidate pair
in this batch.

Each Gemma comparison appears as `entity_resolution`. Its safe metadata
includes `job_id`, `candidate_id`, `batch_trace_id`, `pair_attempt`,
`resolver: gemma`, `pipeline`, `request_timeout_seconds`, `prompt_version`,
and `prompt_hash`. Its output records `decision`, `evidence_count`, `model`,
`latency_ms`, `repair_count`, and token `usage`.

### LangSmith content boundary

The batch and xCoRe traces contain IDs, counts, hashes, codes and timings, not
manuscript text, raw xCoRe cache data, secrets, raw database/provider errors or
hidden reasoning. The Gemma pair trace follows `LANGSMITH_TRACE_CONTENT`:

| Mode | Gemma trace content |
| --- | --- |
| `minimal` | Safe identifiers/counts; no manuscript excerpt. |
| `redacted` | Redacted text markers and lengths; no usable manuscript excerpt. |
| `full` | The two compared mentions, offsets, evidence IDs and the two server-built manuscript excerpts. |

The local stack currently uses `full`, so source excerpts for Gemma comparisons
may be visible in LangSmith. This is a deliberate local observability/privacy
setting, not a requirement of entity resolution.

## Verification

- PostgreSQL-backed backend suite: 95 tests, 93 passed and 2 optional skips.
- Separate long-pair regression: passed in 61.203 seconds.
- Frontend: 16 tests passed; ESLint, TypeScript and production Docker builds
  passed.
- Real browser/model smoke covered upload, Stop/Resume, one xCoRe shortcut, one
  Gemma comparison, automatic application, aliases and evidence.
- Live LangSmith roots and child linkage were read back through the configured
  SDK; trace exporter outage tests proved fail-open behavior.
- The developer inspected both batch traces, explained the cumulative count,
  and verified the final independent-scroll Story Bible UI against the running
  book while its resolution worker continued uninterrupted.

## Alternatives and deferred work

- Pure Gemma remains the rollback path and was more accurate in the tiny
  diagnostic, but required more slow LLM calls.
- Qwen3.5 comparison is deferred to a later controlled experiment; Gemma remains
  the fallback model.
- xCoRe groups are not converted into confidence scores. Threshold claims would
  require labelled calibration data.
- Full-book speed and accuracy, undo UI, and a user-facing history of applied
  automatic decisions remain open product/evaluation work.
- Automatic batch continuation removes repeated Resume clicks but does not
  remove the 2,000-candidate discovery ceiling.

## Interview questions

1. Why is a candidate pair not the same as a confirmed identity match?
2. How does StoryGuard reduce Gemma calls, and what quality risk does that
   shortcut introduce?
3. Why are batch `version_totals` cumulative rather than per-batch deltas?
4. How do Stop/Resume attempt fences prevent late model results from corrupting
   saved decisions?
5. Why does evidence validation establish provenance but not semantic identity
   correctness?
