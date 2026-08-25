# EmbeddingGemma Vector Retrieval Candidate

## Experiment metadata

```text
experiment_id: 2026-08-25-vector-gacha-candidate
status: vector-only candidate not promoted
baseline: Elasticsearch BM25
candidate: Elasticsearch kNN with local EmbeddingGemma
candidate_k: 30
primary_split: held-out test
next experiment: hybrid retrieval with RRF
```

## Hypothesis and developer prediction

Vector retrieval should help semantic matches and paraphrases, such as a query
for `car` when the manuscript says only `BMW`. BM25 should remain stronger for
exact names and terms. The developer predicted that quality would depend on the
query and initially considered that vector latency might be lower than BM25.

## Candidate configuration

- provider: Sentence Transformers;
- model: `google/embeddinggemma-300m`;
- revision: `57c266a740f537b4dc058e1b0cda161fd15afa75`;
- StoryGuard version: `embeddinggemma-v1`;
- dimensions: `768`;
- normalized document and query embeddings;
- Elasticsearch `dense_vector` with cosine similarity;
- mandatory `project_id`, `manuscript_version_id`, and `embedding_version`
  filters inside the kNN query;
- candidate K: `30`, number of candidates: `100`;
- deterministic final ordering by score descending and chunk ID ascending.

The model is local at inference time. Its gated Hugging Face download requires
an accepted license and `HF_TOKEN`; the model files are cached in a shared
Docker volume.

## Dataset and reproducibility

The candidate reused the fixed BM25 benchmark without changing its corpus,
queries, qrels, split, parser, or chunking:

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

## Quality results

| Split | Strategy | Recall@1 | Recall@5 | Recall@10 | Recall@20 | MRR@10 |
|---|---|---:|---:|---:|---:|---:|
| Dev | BM25 | 0.6695 | 0.9661 | 0.9831 | 1.0000 | 0.8347 |
| Dev | Vector | 0.6017 | 0.9153 | 0.9661 | 0.9831 | 0.7654 |
| Test | BM25 | 0.5300 | 0.7940 | 0.8734 | 0.9270 | 0.6700 |
| Test | Vector | 0.5129 | 0.8176 | 0.8691 | 0.9270 | 0.6612 |
| All | BM25 | 0.5582 | 0.8288 | 0.8955 | 0.9418 | 0.7033 |
| All | Vector | 0.5308 | 0.8373 | 0.8887 | 0.9384 | 0.6822 |

Vector improved held-out Recall@5 by `0.0236`, but regressed held-out
Recall@1, Recall@10, and MRR@10. Across all queries it improved only Recall@5.
The number of queries whose labeled evidence was not rank 1 increased from
`117` to `127`.

## Latency and indexing cost

Local CPU compare run:

```text
BM25 median query latency:            11.62 ms
Vector warm median query latency:    152.75 ms
Vector cold query latency:         2,621.67 ms
Initial model load:                31,526.31 ms
Document embedding:            1,279,628.31 ms
Document throughput:                   1.65 chunks/s
```

The repeat run produced a `147.32 ms` vector warm median and `1.63 chunks/s`.
There were no paid API calls. Query embedding made warm vector retrieval about
13 times slower than BM25 on this hardware; cold loading was about 226 times
slower. Document embedding added roughly 21 minutes 20 seconds to full-corpus
indexing.

## Failure analysis

The semantic Anne diagnostic improved:

```text
How did Anne respond when Mrs. Barry did not acknowledge the correct spelling
of her name?
BM25 rank: 16
Vector rank: 9
```

Vector connected `did not acknowledge` with `not hearing or not comprehending`
and `correct spelling` with `Spelled with an E`, moving genuine evidence into
the Top 10.

The reverse also occurred. Examples included:

- the bright brass plate question regressed from BM25 rank 1 to vector rank 10;
- the fair young girl question regressed from BM25 rank 2 to absent from the
  vector Top 30;
- 155 of 292 queries changed first-relevant rank in either direction.

The strategies therefore have complementary strengths, but this experiment
does not prove that combining them will improve aggregate quality. Fusion must
be evaluated as another candidate.

## Reliability, security, and UI verification

- backend suite with PostgreSQL and Elasticsearch: 24 tests passed;
- frontend unit tests: 5 passed; lint and production build passed;
- unmocked Playwright upload flow: 1 test passed;
- browser upload reached the real API, Taskiq worker, MinIO, PostgreSQL, vector
  indexing, completed job, and chapter viewer;
- embedding failures return a safe job error and do not replace the previous
  ready manuscript version;
- incompatible, non-finite, or wrong-dimension vectors fail closed;
- project, manuscript-version, and embedding-version scope is enforced in
  Elasticsearch;
- no LangSmith traces were produced because no LLM call was involved.

## Developer conclusion and discussion

The developer concluded that different queries favor different retrievers and
that StoryGuard needs hybrid search. This correctly identifies complementary
failure modes rather than choosing a retriever from one average metric.

The correction is that hybrid retrieval is a hypothesis, not an automatic
improvement. Lexical and vector scores are not directly comparable, so the next
experiment must use an explicit fusion method and measure both regressions and
latency.

## Decision

Keep BM25 as the primary baseline. Do not promote vector-only retrieval. Run a
new candidate experiment for hybrid BM25 plus vector retrieval using reciprocal
rank fusion, as specified by Lesson 3.3.

