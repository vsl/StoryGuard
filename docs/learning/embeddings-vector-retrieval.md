# Embeddings and Vector Retrieval

## Mental model

```text
text --embedding model version V--> vector in vector space V
query --the same model version V--> query vector
query vector --cosine kNN within allowed scope--> ranked chunks
```

Embedding coordinates are model-specific. Vectors from different models or
incompatible model revisions cannot be compared meaningfully. StoryGuard
therefore stores and filters `embedding_version` rather than silently mixing
vector spaces.

Vector retrieval ranks semantic proximity, not truth. A nearby chunk may discuss
the same topic without supporting the requested claim. Downstream StoryGuard
features must still require manuscript evidence.

## StoryGuard implementation

`config/models.yaml` pins the embedding repository, immutable revision,
StoryGuard version, and dimension. `backend/app/ai/embeddings.py` loads the local
Sentence Transformers model lazily and provides separate document and query
encoding paths. Every returned vector must contain 768 finite values.

`backend/app/ai/retrieval.py` defines the `storyguard-chunks-v2` mapping with a
cosine `dense_vector`. `retrieve_vector`:

- validates query and Top-K;
- embeds the query outside the async event loop;
- runs Elasticsearch kNN;
- filters by project, manuscript version, and embedding version inside the
  query;
- excludes stored vectors from the response;
- returns deterministic ranked `RetrievedChunk` values.

There is one concrete local provider and no speculative provider interface or
Elasticsearch SDK wrapper.

## Ingestion and publication flow

```text
browser upload
  -> FastAPI manuscript version + queued job
  -> Taskiq worker downloads from MinIO
  -> parse chapters/scenes/chunks
  -> persist narrative rows in PostgreSQL
  -> embed all chunks locally
  -> replace the version-scoped Elasticsearch documents
  -> persist embedding_version on chunk rows
  -> mark version ready and publish it as current
```

Embedding failure marks the new version and job failed with a safe error. The
previous ready version stays current. Elasticsearch indexing failure follows
the same publication invariant. PostgreSQL remains the source of truth and the
Elasticsearch index is rebuildable derived data.

The existing manuscript UI needed no new retrieval screen in Lesson 3.2. Its
real upload/job/chapter path now exercises vector indexing, and the copy refers
to the general manuscript search index. A Playwright test proved the full flow
without intercepting application API requests.

## Why local EmbeddingGemma

- manuscript text remains local during inference;
- model identity and revision are reproducible;
- separate query/document encoders match the retrieval task;
- 768 dimensions are supported by the Elasticsearch mapping;
- the shared Docker model cache avoids downloading weights for every worker
  restart.

The trade-off is local CPU and memory cost. The gated initial download also
requires license acceptance and a read-only Hugging Face token.

## Benchmark result

The candidate reused the fixed Gacha benchmark: 10 books, 2,108 StoryGuard
chunks, 292 queries, 324 qrels, and the same dev/test split and fingerprints as
BM25.

| Strategy | Recall@1 | Recall@5 | Recall@10 | Recall@20 | MRR@10 |
|---|---:|---:|---:|---:|---:|
| BM25 | 0.5582 | 0.8288 | 0.8955 | 0.9418 | 0.7033 |
| Vector | 0.5308 | 0.8373 | 0.8887 | 0.9384 | 0.6822 |

Vector improved aggregate Recall@5 but regressed the other aggregate quality
metrics. It moved the semantic Anne diagnostic from rank 16 to rank 9, while
other exact-detail questions regressed. Different queries favored different
retrievers.

## Latency and cost

```text
BM25 median query:           11.62 ms
Vector warm median query:   152.75 ms
Vector cold query:        2,621.67 ms
2,108 document embeddings:  about 21m 20s
throughput:                  about 1.65 chunks/s
paid API cost:               zero
```

Vector latency was not lower. BM25 sends the query directly to Elasticsearch;
vector retrieval first runs a 300M-parameter local model. Index-time embedding
cost and query-time embedding latency are separate operational concerns.

## Failure and security invariants

- Never compare or retrieve across incompatible embedding versions.
- Never filter project/version scope after global Top-K retrieval.
- Never publish a new manuscript version before embeddings and indexing
  succeed.
- Never expose model paths, tokens, or raw internal exceptions in job errors.
- Never treat semantic similarity as evidence correctness.
- Reject wrong-dimension and non-finite vectors before indexing.

## Alternatives and next step

- Vector-only retrieval was not promoted because aggregate quality and latency
  did not beat the fixed BM25 baseline.
- Replacing the local model with an API embedding could reduce local compute but
  adds manuscript privacy, network, availability, and monetary costs.
- Comparing raw BM25 and cosine scores directly would be invalid because their
  scales have different meanings.
- Hybrid retrieval with reciprocal rank fusion is the next experiment. RRF
  combines ranks rather than incomparable raw scores, but it must still prove
  quality and latency on the same benchmark.

## Interview questions

1. Why can vectors from two embedding models not be mixed safely?
2. Why does StoryGuard use separate query and document encoders?
3. Why must project and manuscript-version filters be inside the kNN query?
4. Why can vector retrieval improve paraphrases but regress exact details?
5. Why are vector similarity and evidence correctness different concepts?
6. What is the difference between index-time and query-time embedding cost?
7. Why should hybrid fusion use ranks instead of adding raw BM25 and cosine
   scores?
8. What would make you promote a hybrid candidate over the BM25 baseline?

