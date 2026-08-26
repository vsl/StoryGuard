# Hybrid Retrieval with Reciprocal Rank Fusion

## Mental model

BM25 and vector similarity scores have unrelated scales. Reciprocal rank fusion
combines only their rank positions:

```text
RRF(chunk) = sum(1 / (rank_constant + rank_in_result_list))
```

StoryGuard's promoted baseline uses a rank constant of 60 and a Top-30 window
from each branch. A chunk ranked by both retrievers receives two contributions;
a chunk absent from a branch receives none from that branch.

RRF measures agreement, not truth. Two retrievers may agree on an irrelevant
chunk, and a strong lexical result may regress when the vector branch ranks it
poorly or omits it.

## StoryGuard implementation

`backend/app/ai/retrieval.py` runs the existing project- and
manuscript-version-scoped BM25 and vector retrievers concurrently. It:

- validates final Top-K and experimentable RRF parameters;
- retrieves a bounded candidate window from both branches;
- deduplicates by server-owned `chunk_id`;
- replaces incomparable raw scores with RRF scores;
- sorts by RRF score descending and `chunk_id` ascending.

The `chunk_id` tie-break is deliberate. Equal-score results are reproducible
across runs, which makes tests, metrics, regressions, and production failures
diagnosable. Retriever execution order does not decide the final ranking.

```text
query + project_id + manuscript_version_id
  -> BM25 Top-30 ---------+
  -> vector Top-30 ------+-> deduplicate -> RRF -> deterministic Top-K
```

Failure of either branch fails the hybrid call. Silent fallback is postponed to
the later bounded retrieval-fallback lesson.

## Prediction and actual result

The developer predicted that hybrid would improve the quality metrics and be
slower than vector-only retrieval. That held for every primary held-out quality
metric and warm latency.

The prediction that the Anne evidence would improve beyond vector rank 9 did
not hold:

```text
BM25 rank: 16
Vector rank: 9
Hybrid rank: 10
```

The Anne chunk received both RRF contributions, but competing chunks received
stronger combined scores. This is the concrete reason that intersection does
not guarantee improvement for an individual query.

## Held-out experiment result

| Strategy | Recall@1 | Recall@5 | Recall@10 | Recall@20 | MRR@10 |
|---|---:|---:|---:|---:|---:|
| BM25 | 0.5300 | 0.7940 | 0.8734 | 0.9270 | 0.6700 |
| Vector | 0.5129 | 0.8176 | 0.8691 | 0.9270 | 0.6612 |
| Hybrid RRF | **0.5601** | **0.8541** | **0.9056** | **0.9635** | **0.7126** |

Hybrid improved 83 query ranks versus BM25, regressed 46, and left 163
unchanged. It was promoted because it won the predefined held-out aggregate
metrics, not because it won every query. BM25 and vector remain available for
experiments and failure diagnosis.

## Latency and cost

Representative warm medians from the same local compare run were:

```text
BM25:       about 8.8 ms
Vector:    about 61.1 ms
Hybrid:    about 71.3 ms
paid cost: zero
```

BM25 and vector execute concurrently, so hybrid latency follows the slower
vector branch plus Elasticsearch and fusion overhead rather than adding both
branch latencies. A cold query still pays the local model-load cost.

## Reusable experiment document index

Repeated experiments no longer recompute the same document embeddings. The
benchmark derives an immutable Elasticsearch index name from:

- chunk output hash and parser/tokenizer/chunking versions;
- embedding repository, immutable revision, StoryGuard version, dimension, and
  document encoding settings;
- Sentence Transformers and Torch versions;
- Elasticsearch mapping and version.

On a cache hit, the harness verifies the exact document count and requires every
document to have the current `embedding_version`. It then skips document
embedding and index construction. A partial index is deleted and rebuilt under
the exact guarded experiment prefix.

The validation cache miss spent about 998 seconds embedding documents and 10
seconds building the index. The immediate repeat reported a cache hit, skipped
both stages, and preserved every quality metric and diagnostic rank.

Query embeddings intentionally remain uncached. This keeps query latency honest
and ensures that query/model/rewrite experiments execute their real query path.

The cache is stored in the existing Elasticsearch Docker volume. It survives
container recreation but not explicit volume deletion. Old fingerprinted
indexes are cleaned manually if disk usage eventually warrants it; no retention
service was added speculatively.

## Security, reliability, and observability

- Project and manuscript-version filters stay inside both retrieval branches.
- Vector retrieval additionally enforces `embedding_version` inside kNN.
- The cache never shares a mutable index between different fingerprints.
- An incomplete cache cannot be treated as valid.
- The experiment dataset contains public benchmark stories, not user manuscript
  data.
- No LangSmith traces exist because retrieval and fusion made no LLM calls.
- Twenty-seven backend tests passed against live PostgreSQL and Elasticsearch.

## Alternatives

- Adding raw BM25 and cosine scores was rejected because the scales are not
  comparable.
- A new vector-cache file format and Docker volume were unnecessary;
  Elasticsearch already persists exactly the indexed artifact the experiment
  needs.
- Query embedding caching was skipped because its cost is small and it would
  invalidate end-to-end query latency measurements.
- Reranking is a separate precision stage in Lesson 3.4 rather than part of RRF.

## Interview questions

1. Why is adding BM25 and cosine scores directly invalid?
2. How does RRF reward agreement without calibrating raw scores?
3. Why can hybrid improve aggregate Recall@K while regressing individual exact-detail queries?
4. Why does StoryGuard use a deterministic `chunk_id` tie-break?
5. Which inputs must invalidate a cached document-embedding index?
6. Why are document embeddings cached while query embeddings remain live in this benchmark?
7. Why is a reranker a separate stage after hybrid candidate generation?
