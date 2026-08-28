# AI Experiment Lab

## Mental model

An experiment changes one variable while holding the evaluation data and every
other configuration value constant:

```text
fixed labeled queries + fixed hybrid retrieval
  -> baseline: reranker off
  -> candidate: reranker on
  -> compare quality, latency, cost, and failures
```

Smoke and development runs diagnose changes quickly. They cannot promote a
candidate. Promotion requires the existing 233-query held-out CLI evaluation.

## StoryGuard implementation

`backend/app/ai/experiment_suites.py` defines the controlled UI suites and the
only allowed baseline/candidate pair. `backend/app/ai/experiments.py` creates an
immutable snapshot containing exact query IDs, dataset revision, manifest hash,
retrieval settings, and reranker state.

`backend/app/api/experiments.py` persists runs in PostgreSQL and queues them
through Taskiq/RabbitMQ. PostgreSQL is the source of truth; RabbitMQ contains
only uncompleted delivery work. A database uniqueness constraint permits one
active UI experiment.

`backend/app/queue/tasks/experiments.py` orchestrates this phased workflow:

```text
prepare index
  -> candidate shards
  -> reranker shards
  -> aggregate
  -> persist metrics/failures
```

The long-lived Taskiq worker does not load retrieval models. Every phase runs
`backend/scripts/bm25_experiment.py` in a fresh Python subprocess. Shard
artifacts are restartable, and process exit releases phase-owned model memory.
LangGraph is intentionally absent because this is deterministic job
orchestration, not conditional AI reasoning.

The Experiment Lab UI exposes only fixed Smoke/Development suites:

- Gacha Smoke: 3 queries;
- Gacha Development Alice: 30 queries;
- Gacha Development Christmas: 29 queries;
- Gacha Development All: 59 queries.

Uploaded manuscripts are excluded because they have no labeled ground truth.
The UI has no arbitrary model/config IDs and no promotion action.

## Developer checkpoint

The developer ran `gacha-dev-alice` through the real UI. PostgreSQL run
`fe8900e0-b6f3-4e3e-ab47-95dc17cfb373` completed all 8 units in one attempt:
one index preparation, three candidate shards, three reranker shards, and one
aggregation. Total wall time was about 22 minutes 24 seconds.

| Metric | Hybrid RRF | Hybrid RRF + reranker |
|---|---:|---:|
| Recall@10 | 1.0000 | 1.0000 |
| MRR@10 | 0.8167 | 1.0000 |
| p50 latency | 107 ms | 41,508 ms |
| p95 latency | 339 ms | 46,323 ms |
| API cost | $0 | $0 |

The reranker improved relevant-result order but did not improve recall because
Hybrid RRF already retrieved the relevant chunks. The latency regression of
roughly 387x at p50 and 137x at p95 made the candidate unacceptable.

During reranking, the container used 3 GiB and had 59 processes/threads. Two
observed shards used different subprocess PIDs (`14391`, then `24178`) while
the Taskiq PID remained `55388`. After completion, `bm25_experiment.py`
disappeared, the container fell to 7 processes/threads, CPU fell from about
1147% to 0.36%, and memory fell to 1.858 GiB. This confirms phase-process
isolation and partial memory release; a pre-run baseline would be required to
attribute the remaining memory precisely.

The developer concluded that shard isolation solves cumulative model-memory
growth for the current local workflow and that the post-run worker footprint is
acceptable. The reranker candidate was rejected because important operational
metrics worsened.

## Observability and failure diagnosis

The completed run persisted eight LangSmith trace IDs, one per phase:

- `14d4d1a7-96d2-5885-9cce-87a313d3cb7e`
- `04fbe2d8-e73f-59fc-80a1-880c11bd7db8`
- `280a3deb-c951-5b52-9444-458dccc32321`
- `fb01719e-ec86-5315-b345-14a92cf8e43a`
- `730970fb-fc8b-50a3-bb23-76b8aab818ab`
- `c3fd5696-a94f-532c-af77-de656cf8ec33`
- `6f839702-3d0a-5cc6-8adc-74c5dae8c201`
- `6368163a-5895-5b9a-914d-b3f048ef805c`

LangSmith is optional observability, not durable experiment storage. If trace
export fails or retention expires, PostgreSQL still owns the immutable config,
progress, metrics, failure records, and safe trace references.

Important failure classes are:

- queue unavailable: persist a safe terminal error and release the active slot;
- phase timeout/failure: kill the subprocess and persist a generic safe error;
- candidate-pool miss: the reranker cannot recover evidence absent from Top-30;
- reranker regression: relevant evidence moves to a worse rank;
- duplicate task delivery: completed/failed runs are no-ops and phase artifacts
  support restart.

## Tests and operational checks

- Backend suite: 39 passed, 12 opt-in integrations skipped.
- PostgreSQL experiment integration: 5 passed.
- Frontend: 6 tests passed; lint and production build passed.
- Real browser-to-backend/worker/storage experiment passed without API mocks.
- Docker readiness returned 200 with PostgreSQL, MinIO, and Elasticsearch up.
- All persisted trace IDs checked during verification resolved in LangSmith.
- Integration cleanup was verified not to delete a real experiment run.

## Alternatives and exclusions

- LangGraph was unnecessary for a fixed sequence of restartable phases.
- A generic experiment engine was skipped; the UI supports one evaluated
  retrieval comparison.
- Full held-out evaluation remains the phased CLI workflow so a laptop is not
  forced to retain the complete experiment in memory.
- No promotion endpoint exists. A diagnostic run cannot silently alter
  production AI behavior.
- No uploaded-story evaluation exists without trustworthy labeled queries.

## Interview questions

1. Why must an experiment change only one variable?
2. Why can a reranker improve MRR without improving Recall@10?
3. Why is PostgreSQL the source of truth rather than RabbitMQ or LangSmith?
4. Why are fresh subprocesses useful for local model experiments?
5. Why are Smoke and Development results insufficient for promotion?
6. What distinguishes a candidate-pool miss from a reranker regression?
7. Why is a 387x latency regression more important than a small MRR gain here?
