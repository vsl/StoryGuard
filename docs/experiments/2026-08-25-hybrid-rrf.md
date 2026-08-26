# Hybrid Retrieval with Reciprocal Rank Fusion

## Hypothesis

BM25 and vector retrieval make complementary ranking errors. Reciprocal rank
fusion may improve retrieval quality by rewarding chunks ranked by both
strategies without adding their incomparable raw scores.

## Developer prediction

The developer predicted that hybrid retrieval would beat BM25 and vector-only
retrieval on Recall@5, Recall@10, and MRR@10, improve the Anne diagnostic beyond
vector rank 9, and be slower than vector-only retrieval.

## Baseline and candidate

```text
experiment_id: 2026-08-25-hybrid-rrf-gacha
baseline: Elasticsearch BM25
comparative baseline: Elasticsearch kNN with local EmbeddingGemma
candidate: parallel BM25 + vector retrieval fused with RRF
candidate_k: 30 per branch
rrf_rank_constant: 60
rrf_rank_window: 30
status: promoted as the first-stage retrieval baseline
```

The candidate runs the existing project- and manuscript-version-scoped BM25
and vector retrievers concurrently, deduplicates by `chunk_id`, assigns each
chunk `sum(1 / (60 + rank))`, and sorts by RRF score descending with
`chunk_id` as the deterministic tie-breaker.

## Dataset and reproducibility

```text
dataset: feyninc/gacha
revision: 076b8b186236941df371a8d9b14be4cb4c7498fb
books: 10
queries: 292
chunks: 2,108
qrels: 324
parser/chunking: v2 / storyguard-700-900-v1
queries:   4ac514d0987cfa6f14930e88c6790eaa3894b6aec4093a908b2608785fc61ce9
documents: b911bb6f249adb333a319c34d75625b1023390b429121778307b9a4d392c92ac
chunks:    6d26f682465c6e9badf51363a79894e5d790910bf7dc4cc53d7b2a55afc7b9f9
qrels:     27a9512e8e90284b5b4c25613d87fc6308b4a690fa3c2d6f555032b209a619bf
```

BM25, vector, and hybrid used the same corpus, queries, qrels, scopes, query
order, document embeddings, and disposable Elasticsearch index.

## Quality metrics

The held-out test split was the primary comparison.

| Strategy | Recall@1 | Recall@5 | Recall@10 | Recall@20 | MRR@10 |
|---|---:|---:|---:|---:|---:|
| BM25 | 0.5300 | 0.7940 | 0.8734 | 0.9270 | 0.6700 |
| Vector | 0.5129 | 0.8176 | 0.8691 | 0.9270 | 0.6612 |
| Hybrid RRF | **0.5601** | **0.8541** | **0.9056** | **0.9635** | **0.7126** |

Aggregate results across dev and test:

| Strategy | Recall@1 | Recall@5 | Recall@10 | Recall@20 | MRR@10 |
|---|---:|---:|---:|---:|---:|
| BM25 | 0.5582 | 0.8288 | 0.8955 | 0.9418 | 0.7033 |
| Vector | 0.5308 | 0.8373 | 0.8887 | 0.9384 | 0.6822 |
| Hybrid RRF | **0.5856** | **0.8767** | **0.9212** | **0.9709** | **0.7371** |

Hybrid also reduced the number of queries without labeled evidence at rank 1
from 117 for BM25 and 127 for vector to 109.

On the dev split, hybrid Recall@5, Recall@10, and Recall@20 tied BM25, while
hybrid MRR@10 was 0.8338 versus BM25's 0.8347. The candidate therefore did not
win every metric on every split even though it won all primary held-out metrics.

## Latency and cost

Local CPU compare run:

```text
BM25 median query latency:           8.79 ms
Vector warm median query latency:   61.12 ms
Vector cold query latency:       2,356.20 ms
Hybrid warm median latency:         71.32 ms
Initial model load:               5,672.56 ms
Document embedding:             849,488.68 ms
Document throughput:                  2.48 chunks/s
paid API cost:                         0
```

Hybrid was about 10.2 ms slower than warm vector-only retrieval and about 8.1
times the BM25 median. BM25 and vector ran concurrently inside hybrid, so their
latencies were not simply added. A separate cold hybrid query was not measured;
it would still pay the embedding model's cold-load cost.

## Failure analysis

Compared with BM25, hybrid changed the first labeled rank for 129 of 292
queries: 83 improved and 46 regressed.

Representative improvements:

- the Scrooge nephew `Keep it` question moved from BM25 rank 2 to hybrid rank 1;
- the Marley chain-items question moved from BM25 rank 3 to hybrid rank 1;
- the Ghost of Christmas Past question moved from BM25 rank 11 to hybrid rank 9.

Representative regressions:

- the fair young girl question moved from BM25 rank 2 to hybrid rank 20 because
  vector did not retrieve the labeled chunk in its Top 30;
- the bright brass plate question moved from BM25 rank 1 and vector rank 10 to
  hybrid rank 4;
- several BM25 rank-1 exact-detail results moved to hybrid rank 2 or 3.

The Anne diagnostic was:

```text
BM25 rank: 16
Vector rank: 9
Hybrid rank: 10
```

The relevant chunk received contributions from both lists, but other chunks
received stronger combined RRF scores. Agreement is a ranking signal, not a
relevance guarantee.

## Reliability, security, and observability

- 25 backend tests passed against live PostgreSQL and Elasticsearch;
- hybrid uses the existing project, manuscript-version, and embedding-version
  filters inside its retrieval branches;
- branch results are deduplicated and ties are deterministic;
- failure of either branch fails hybrid retrieval instead of silently changing
  strategy;
- no fallback was invoked or implemented in this lesson;
- no paid API calls occurred;
- no LangSmith trace IDs exist because the experiment made no LLM calls.

## Developer conclusion

The developer chose to promote hybrid because it won the primary held-out
aggregate quality metrics.

## Discussion and correction

Promotion is supported by the predefined held-out Recall@K and MRR results, not
by a claim that hybrid won every query. The candidate has 46 query-level
regressions, a small dev MRR regression versus BM25, higher latency, and an Anne
rank one position worse than vector-only. These failures remain regression
fixtures and motivation for the separate reranker experiment in Lesson 3.4.

## Decision

Promote RRF hybrid retrieval as StoryGuard's first-stage retrieval baseline for
subsequent lessons. Keep BM25 and vector-only retrieval available for evaluation
and failure diagnosis. Do not add fallback routing, query-type routing, or a
reranker in this lesson.
