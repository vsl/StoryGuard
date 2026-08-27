# Cross-Encoder Reranking

## Mental model

A bi-encoder embeds the query and chunks independently, which makes vector
search fast and indexable. A cross-encoder reads each query/chunk pair together
and can model token-level interactions, but it must execute once for every
candidate pair.

```text
query + project/version scope
  -> Hybrid RRF Top-30
  -> [(query, chunk 1), ..., (query, chunk 30)]
  -> CrossEncoder scores
  -> score desc, chunk_id asc
  -> final Top-K
```

The reranker can change only the order of the Top-30 candidate set. It cannot
recover evidence that retrieval did not include. This is why reranking may
improve Recall@1/5/10 while Recall@30 remains exactly unchanged.

## StoryGuard implementation

`config/models.yaml` pins `BAAI/bge-reranker-v2-m3` to immutable revision
`953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`. The same model lifecycle used for
embeddings now loads the reranker configuration.

`backend/app/ai/reranking.py` provides the local cross-encoder implementation.
It:

- lazily loads the pinned Sentence Transformers `CrossEncoder`;
- uses raw logits rather than converting scores into fake probabilities;
- scores a bounded batch of query/chunk pairs;
- requires one finite score per candidate;
- applies a deterministic `chunk_id` tie-break;
- caches one loaded model per process.

`backend/app/ai/retrieval.py::retrieve_hybrid_reranked` requests exactly 30
scoped hybrid candidates and runs CPU-heavy reranking through
`asyncio.to_thread`, so inference does not block the event loop. The reranker
receives already scoped `RetrievedChunk` objects and is not allowed to add or
replace membership.

There were no API, database, or schema changes. The normal application baseline
remains Hybrid RRF. Cross-encoder reranking is promoted only as an optional
quality mode; later UI integration must use the Docker backend/worker and a
background job rather than a long synchronous request.

## Security and reliability invariants

- Project and manuscript-version isolation is enforced during retrieval before
  manuscript text reaches the reranker.
- Manuscript text is scored as untrusted data, not interpreted as instructions.
- Candidate membership must remain identical after reranking.
- Empty queries, invalid Top-K values, non-finite scores, and score-count
  mismatches fail explicitly.
- Stable ordering makes eval regressions reproducible.
- Important claims still require server-issued evidence IDs; reranker scores
  are relevance signals, not evidence or calibrated confidence.

## Held-out experiment

The approved evaluation used all 233 held-out test queries from immutable
`feyninc/gacha@076b8b186236941df371a8d9b14be4cb4c7498fb`.

| Metric | Hybrid RRF | Hybrid + reranker |
|---|---:|---:|
| Recall@1 | 0.5601 | **0.7511** |
| Recall@5 | 0.8541 | **0.9206** |
| Recall@10 | 0.9056 | **0.9614** |
| Recall@20 | 0.9635 | **0.9721** |
| Recall@30 | 0.9764 | 0.9764 |
| MRR@10 | 0.7126 | **0.8544** |
| Median local latency | 147 ms | 10,917 ms |

The reranker changed the relevant-evidence rank for 94 queries: 71 improved and
23 regressed. Five queries had no relevant chunk in the original Top-30, so the
reranker could not repair them. Paid API cost was zero.

The developer correctly predicted that early-rank metrics should improve,
Recall@30 should not change, and latency should regress. The magnitude of the
latency regression made default promotion inappropriate.

## Promotion decision

StoryGuard keeps Hybrid RRF as the default retrieval path. Cross-encoder
reranking is an opt-in quality mode for workflows where additional relevance is
worth substantial latency. It is not a fallback: if evidence is missing from
Top-30, a larger or better candidate-retrieval stage is required.

## Reusable experiment cache

The resource-heavy evaluation is split into independently restartable phases:

```text
candidate shard -> persisted JSONL -> reranker shard -> persisted JSONL
                                        all shards -> aggregate.json
```

Candidate and reranker artifacts use separate fingerprints:

- retrieval, dataset, chunking, embeddings, RRF, candidate count, environment,
  and shard configuration invalidate candidates;
- candidate fingerprint plus reranker repository/revision/version and runtime
  invalidate reranker results;
- metric/report changes can re-aggregate existing results without model calls.

Artifacts and Hugging Face files live under ignored project `.local/`, not an
unmanaged system temporary directory. Exact repeats return `already_complete`.
Changing only the reranker revision reuses candidates but creates a new result
directory.

## Docker versus native experiments

A ten-query runtime benchmark compared project bind mounts, a temporary Docker
named volume, and native execution. Rankings matched exactly for all ten
queries.

| Runtime | Hybrid median | Full reranked median |
|---|---:|---:|
| Docker + bind cache | 155 ms | 51.13 s |
| Docker + named-volume cache | 153 ms | 51.46 s |
| Native + project cache | 168 ms | **20.57 s** |

Named-volume model loading was only 5-6% faster and did not improve inference.
Native reranking was about 2.5 times faster in this run. Therefore Docker
Compose remains canonical for UI, API, workers, integration tests, and normal
experiments. Native is allowed only for heavy local reranker experiments with
pinned versions, fingerprinted artifacts, and a small Docker equivalence check.
Production capacity decisions must use the target container and hardware.

The full runtime report is
`docs/experiments/2026-08-27-runtime-storage-benchmark.md`.

## Failure and diagnostic model

```text
relevant chunk absent from Top-30
  -> reranker never sees it
  -> Recall@30 miss remains
  -> inspect candidate retrieval, not reranker score
```

A regression where relevant evidence moves from rank 1 to rank 3 is a reranker
ranking failure. A query with no relevant Top-30 candidate is a retrieval
failure. Keeping these categories separate prevents tuning the wrong stage.

## Alternatives and trade-offs

- Making the reranker the default was rejected because current latency is too
  high for interactive use.
- Increasing the candidate pool may improve candidate recall but increases
  cross-encoder cost approximately with the number of pairs and requires a new
  experiment.
- A hosted reranker or accelerated target may reduce latency but adds monetary,
  privacy, deployment, and availability trade-offs.
- A Docker named model volume was rejected as the default because its small
  cold-load gain did not justify hidden duplicated storage.
- Semantic result caching was not added. Exact fingerprinted experiment reuse
  is sufficient and cannot silently cross model or manuscript versions.

## Tests and observability

The retrieval/reranker suite covers finite scores, deterministic ties, bounded
candidate membership, project/version scope, deterministic sharding, cache
version separation, and exact aggregation. Fourteen tests passed natively and
inside Docker; the final quick run skipped the opt-in live-Elasticsearch test.
The live retrieval integration suite had passed earlier in the lesson.

There are no LangSmith traces because embeddings, Elasticsearch, RRF, and the
cross-encoder make no LLM calls. LangSmith tracing begins in Lesson 4.1.

## Interview questions

1. Why can a cross-encoder improve Recall@5 without changing Recall@30?
2. Why is cross-encoder reranking more expensive than bi-encoder retrieval?
3. How do you distinguish a candidate-retrieval miss from a reranker regression?
4. Which inputs must invalidate candidate cache versus reranker-result cache?
5. Why did StoryGuard keep reranking opt-in despite its large MRR improvement?

