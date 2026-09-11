# Structured Story Memory

## Mental model

```text
manuscript chunk + resolved entities + server-issued evidence IDs
  -> model proposes facts, events, relationships
  -> schema, scope, entity, and citation validation
  -> one repair, otherwise omit the invalid chunk output
  -> PostgreSQL records linked to exact manuscript evidence
  -> Story Bible and Timeline
```

An extracted record is a proposal. The cited evidence is the basis on which a
reader judges it; it does not prove the model interpreted the passage correctly.
Coverage reports processing progress, not whether the manuscript contains every
event that was not extracted.

## StoryGuard implementation

`POST /api/projects/{project_id}/structured-memory/run` in
`backend/app/api/structured_memory.py` requires a completed entity-resolution
job, creates a version-pinned `JobRun`, and enqueues it through Taskiq.
`backend/app/queue/tasks/structured_memory.py` supplies each chunk to
`backend/app/ai/structured_memory.py`, then persists accepted output through
`backend/app/structured_memory.py`.

The worker sends only entities that occur in the chunk and an evidence block
whose ID and offsets were issued by the server. Validation accepts citations
only from that block, verifies entity references, rejects unsupported taxonomy
and inconsistent relationship event roles, and permits one repair. PostgreSQL
stores facts, events, relationships, associations, evidence, chunk results,
prompt/model provenance, latency, token usage, and rejection reasons.

Events have two independent orderings. `narrative_chapter_ordinal` is where the
reader encounters an event; `chronological_time_normalized` is when it happens
inside the story. The Timeline can therefore show the same data by narrative or
chronological order. A relationship starts or ends through an event, preserving
both the change event and the relationship's current status.

The browser path is `frontend/components/core-screens.tsx` to the scoped read
APIs. The Story memory card exposes coverage as `completed/total chunks`, plus
failed chunks and stored record counts. Selecting Source evidence opens the
stored passage in the manuscript.

## Developer checkpoint

The Timeline event “Mara and Ilya divorced” was supported by the exact source:
“On March 2, 2024, Mara and Ilya divorced in Porto.” The developer correctly
identified this as support for the divorce claim, and distinguished Chapter 1
(narrative position) from March 2, 2024 (chronological story time).

The screenshot showed the coverage in the Story memory card as `0/2 chunks ·
1 failed`. This is a run-progress/partial-failure signal, not a claim that the
book contains no other events. The developer correctly concluded that a missing
record cannot establish that an event is absent from the manuscript.

## Safety, failure, and observability

- Every job and read query is constrained to the project and current manuscript
  version. A changed version or entity-resolution fingerprint fences worker
  persistence.
- The model cannot invent an evidence ID. Invalid output receives one repair;
  a repeated failure is recorded safely for that chunk while usable prior output
  remains available.
- Exact duplicates from overlapping chunks collapse. A retry cannot replace a
  usable run with less completed chunk coverage.
- Relationship updates require a compatible accepted start/end event and shared
  evidence, so a relationship is never inferred from an unlinked event.
- Structured-memory trace inputs and outputs are designed for LangSmith, but
  tracing was disabled during the local smoke check, so this lesson has no
  trace ID. PostgreSQL is the audit source of truth.

## Evaluation and trade-off

The promoted V7 structured-memory experiment achieved semantic macro F1
`0.715`, with `1/12` failed cases. The stricter V8 verifier regressed to `0.200`
with `9/12` failures and was not promoted. Both figures are a small controlled
evaluation, not a quality guarantee for a full manuscript.

The smoke check processed one of two chunks, safely retained the divorce event,
and rejected the relationship when the event output omitted both required roles.
This favors evidence integrity over recall. The local run incurred no API cost;
model latency and token usage are stored per chunk for later comparison.

Deferred: broad continuity detection, direct Story QA, version comparison, and
more extraction categories. Those require later lessons and separate evidence.

## Interview questions

1. Why does a valid evidence ID not guarantee that an extracted event is true?
2. Why store narrative order separately from chronological story time?
3. How does StoryGuard keep a failed chunk from corrupting a usable story-memory run?
4. What must be true before an event-backed relationship can be persisted?
5. Why is chunk coverage not recall?
