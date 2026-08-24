# BM25 Retrieval Baseline

## Mental model

```text
allowed candidates = filter(project_id, manuscript_version_id)
ranked evidence    = BM25(query, allowed candidates)
```

BM25 is lexical retrieval. It rewards query-term overlap using term rarity,
saturating term frequency, and document-length normalization. Exact names and
phrases are natural strengths. Synonyms, paraphrases, and conceptual relations
without shared tokens are natural weaknesses.

Retrieval metrics are only as trustworthy as their relevance labels:

```text
observed metric = retriever behavior + ground-truth quality
```

An automatic label means “matches the benchmark rule,” not “a human proved this
chunk is semantically relevant.” Manual failure inspection is still required.

## StoryGuard implementation

`backend/app/queue/tasks/ingestion.py` persists parsed chunks in PostgreSQL and
then calls `replace_version_chunks`. PostgreSQL remains the source of truth;
Elasticsearch is a derived index that can be deleted and rebuilt.

`backend/app/ai/retrieval.py` provides:

- a strict chunk mapping;
- version-scoped delete-and-bulk replacement;
- two short retries after the initial Elasticsearch request;
- a BM25 `match` query;
- mandatory project and manuscript-version filters;
- deterministic `_score` then `chunk_id` ordering;
- typed ranked results containing source metadata and score.

The production index defaults to `storyguard-chunks-v1`. The benchmark sets a
separate disposable index, `storyguard-chunks-gacha-eval-v2`, so experiment
documents, deleted-document tombstones, and index-wide term statistics cannot
change production retrieval or make repeated experiment rankings drift.

The implementation uses the installed async `httpx` client rather than adding
an Elasticsearch SDK or speculative retriever abstraction.

## Request and data flow

```text
MinIO manuscript
  -> Taskiq ingestion
  -> StoryGuard parser
  -> PostgreSQL chapter/scene/chunk rows
  -> version-scoped Elasticsearch bulk index
  -> completed job at stage bm25_indexed
```

```text
question + project_id + manuscript_version_id + top_k
  -> validate question and 1 <= top_k <= 100
  -> bool.must: match(text)
  -> bool.filter: project_id + manuscript_version_id
  -> sort: score descending, chunk_id ascending
  -> BM25-ranked RetrievedChunk values
```

Filtering after global Top-K would be wrong: it could starve the allowed
manuscript of candidates and let another project or old version cross the
retrieval boundary. Scope is therefore enforced inside every Elasticsearch
query. The caller cannot provide arbitrary Elasticsearch DSL.

## Benchmark dataset

The retrieval benchmark uses the pinned Hugging Face dataset:

```text
dataset: feyninc/gacha
revision: 076b8b186236941df371a8d9b14be4cb4c7498fb
configs: corpus, questions
split: train
selection: 10 narrative books
dev: 2 books, 59 questions
test: 8 books, 233 questions
```

The ten full books produce 2,108 StoryGuard chunks with parser `v2`, tokenizer
`regex-v1`, and chunking configuration `storyguard-700-900-v1` (700 target, 900
maximum, 100 overlap).

Each question searches only its corresponding book using deterministic
project/version IDs. All ten books are indexed together so scope isolation is
exercised, but other books are not retrieval candidates.

Gacha is CC BY-NC-SA 4.0. StoryGuard uses it only for this non-commercial
project, preserves attribution/share-alike provenance, and does not assume that
US public-domain status applies in every territory.

## Ground-truth derivation

StoryGuard does not trust a supplied chunk ID:

```text
question
  -> exact chunk-must-contain evidence in the corresponding full book
  -> StoryGuard parser and overlapping chunks
  -> every same-book chunk containing the complete evidence span is relevant
```

All 292 selected questions have non-empty question, answer, and evidence fields.
Each evidence span occurs exactly once in its full book and survives StoryGuard
chunking. The result is 324 qrels: 260 questions have one relevant chunk and 32
have two relevant overlapping chunks.

Recall uses the standard multi-qrel formula:

```text
Recall@K = relevant chunks retrieved in Top-K / all relevant chunks
```

For a question with two relevant chunks, retrieving one at rank 1 contributes
`0.5` to Recall@1. MRR@10 uses the rank of the first labeled chunk and contributes
zero when no labeled chunk appears in the first ten results.

Evidence containment is reproducible but not perfect semantic judgment. A chunk
without the exact span may still answer the question (false negative), and a
chunk containing a short span may lack enough context (false positive). Hard
failures therefore include the question, answer, evidence, and Top-10 previews
for human review.

## BM25 results

Elasticsearch `8.19.19`, default BM25, candidate K `30`:

| Split | Queries | Recall@1 | Recall@5 | Recall@10 | Recall@20 | MRR@10 | Median latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dev | 59 | 0.6695 | 0.9661 | 0.9831 | 1.0000 | 0.8347 | 9.20 ms |
| Held-out test | 233 | 0.5300 | 0.7940 | 0.8734 | 0.9270 | 0.6700 | 8.37 ms |
| All | 292 | 0.5582 | 0.8288 | 0.8955 | 0.9418 | 0.7033 | 8.53 ms |

The held-out test split is the primary reported result. The dev split exists for
future retrieval decisions; candidate selection must not tune against the test
books. Latency is a local single-run measurement, not a production SLA.

## Failure analysis

The inspected held-out question was:

```text
How did Anne respond when Mrs. Barry did not acknowledge the correct spelling
of her name?
```

The gold chunk says:

```text
“Spelled with an E,” gasped Anne...
Mrs. Barry, not hearing or not comprehending...
```

The labeled chunk ranked 16. Manual inspection found that none of the Top-10
chunks answered the question, while the labeled chunk clearly did. This is a
genuine BM25 Top-10 failure, not merely an automatic-label error.

The primary cause is lexical mismatch:

```text
question: did not acknowledge       passage: not hearing or not comprehending
question: correct spelling          passage: Spelled with an E
```

Other chunks sharing common entity terms such as `Anne`, `Mrs. Barry`, and
`Diana` crowded out the relevant scene. This is a concrete hypothesis for the
vector-retrieval comparison, not proof that vector retrieval will win.

## Reproducibility

```text
queries fixture:   4ac514d0987cfa6f14930e88c6790eaa3894b6aec4093a908b2608785fc61ce9
documents fixture: b911bb6f249adb333a319c34d75625b1023390b429121778307b9a4d392c92ac
parsed chunks:     6d26f682465c6e9badf51363a79894e5d790910bf7dc4cc53d7b2a55afc7b9f9
qrels:             27a9512e8e90284b5b4c25613d87fc6308b4a690fa3c2d6f555032b209a619bf
```

BM25, vector, hybrid, and hybrid-plus-reranker candidates must use these same
queries, parsed chunks, qrels, book scopes, and split assignments. If any
fingerprint changes, the results are not a direct candidate comparison.

## Reliability, security, and cost

- Empty questions and invalid Top-K fail before Elasticsearch access.
- Indexed documents must match the requested project and version.
- Elasticsearch 5xx, 429, and transport failures receive bounded retries.
- Partial bulk failures fail ingestion instead of claiming success.
- Reprocessing replaces the complete version scope without duplicates.
- Live integration tests proved zero cross-project and old-version leakage.
- Deterministic tie-breaking and a fresh disposable benchmark index produced
  identical quality metrics across repeated runs.
- The backend suite passed 20 tests; Elasticsearch integration passed 4 tests.
- There were no LLM calls, embeddings, reranking, API charges, or LangSmith
  traces.

## Alternatives and trade-offs

- PostgreSQL full-text search would reduce infrastructure, but Elasticsearch is
  locked for later BM25/vector/hybrid comparison.
- Post-filtering global results is simpler-looking but breaks recall and scope
  isolation.
- One production index per manuscript version could simplify publication but
  creates additional lifecycle work; the current shared, version-filtered
  production index is sufficient at this stage.
- The experiment needs its own index because BM25 term statistics are
  index-wide; sharing the production index made repeated MRR drift.
- Custom BM25 parameters were not tuned. The baseline should remain fixed until
  it is compared fairly with vector and hybrid candidates.

## Interview questions

1. How do TF, IDF, saturation, and length normalization affect BM25 ranking?
2. Why must project/version filters be applied inside the retrieval query?
3. How do multi-qrel Recall@K and MRR@10 measure different ranking behavior?
4. Why does exact evidence containment not guarantee semantic relevance?
5. Why must retrieval candidates share corpus, queries, qrels, and splits?
6. Why does the benchmark use a disposable index while production uses a shared
   version-filtered index?
7. Why might embeddings help the Anne example, and why is that still only a
   hypothesis?
