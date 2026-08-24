# BM25 Retrieval Baseline

## Mental model

```text
allowed candidates = filter(project_id, manuscript_version_id)
ranked evidence    = BM25(query, allowed candidates)
```

BM25 is lexical retrieval: it rewards query-term overlap using term rarity,
saturating term frequency, and document-length normalization. Exact names and
phrases are natural strengths. Synonyms, paraphrases, and conceptual relations
without shared tokens are natural weaknesses.

Retrieval metrics are only as trustworthy as their relevance labels:

```text
observed metric = retriever behavior + ground-truth quality
```

## StoryGuard implementation

`backend/app/queue/tasks/ingestion.py` persists parsed chunks in PostgreSQL and
then calls `replace_version_chunks`. PostgreSQL remains the source of truth.
Elasticsearch is a derived index that can be deleted and rebuilt.

`backend/app/ai/retrieval.py` contains the minimum retrieval layer:

- a strict `storyguard-chunks-v1` mapping;
- version-scoped delete-and-bulk replacement;
- two short retries after the initial Elasticsearch request;
- a BM25 `match` query;
- mandatory project and manuscript-version filters;
- typed ranked results containing source metadata and `_score`.

The implementation uses the already installed async `httpx` client instead of
adding an Elasticsearch SDK or a speculative retriever factory.

## Request and data flow

```text
MinIO manuscript
  -> Taskiq ingestion
  -> parser
  -> PostgreSQL chapter/scene/chunk rows
  -> version-scoped Elasticsearch bulk index
  -> completed job at stage bm25_indexed
```

```text
query + project_id + manuscript_version_id + top_k
  -> validate query and 1 <= top_k <= 100
  -> bool.must: match(text)
  -> bool.filter: project_id + manuscript_version_id
  -> BM25-ranked RetrievedChunk values
```

Filtering after global Top-K would be wrong twice: it could starve the allowed
project of candidates, and it would let forbidden projects or old versions enter
the retrieval boundary. StoryGuard therefore enforces scope inside every
Elasticsearch query. No model can provide arbitrary Elasticsearch DSL.

## Index document and evidence lineage

Each indexed document contains:

```text
chunk_id
project_id
manuscript_version_id
chapter_id
chapter_ordinal
scene_id
text
content_hash
```

The identifiers lead back to server-known PostgreSQL rows. This is the basis for
future evidence objects, but citation synthesis and evidence-ID validation are
not part of this lesson.

## Experiment and interpretation

The pinned smoke fixture produced:

- Recall@1: `0.80`;
- MRR: `0.875`;
- median local retrieval latency: `10.10 ms`;
- Recall@5/10/30: `1.00`.

The last three values are not meaningful quality evidence because only three
documents were indexed. Four queries did not place the single labeled chunk at
rank 1. Inspection showed that at least one apparent failure was incomplete
ground truth: the retriever ranked chunk `_3`, which directly described the
station dismantling and arrest, above labeled chunk `_2`, which described the
preceding FCC investigation.

The correct engineering response is not to tune BM25 until the noisy metric
improves. The evaluation data must support multiple relevant chunks and include
enough plausible distractors. The developer explicitly kept BM25 as a
provisional baseline with that limitation.

## Failure cases and reliability

- Empty queries and invalid Top-K fail before Elasticsearch access.
- Documents whose project/version fields disagree with the requested indexing
  scope are rejected.
- Elasticsearch 5xx, 429, and transport failures receive two short retries and
  then surface as a retriable connection failure.
- A partial bulk failure fails the ingestion job instead of claiming success.
- Reprocessing deletes and replaces the complete version scope, avoiding
  duplicate documents.
- Failed versions are not published as current; atomic current-version
  publication remains future lifecycle work.

Live integration checks proved zero cross-project and old-version retrieval
leaks. The full backend suite passed 19 tests. There were no LLM calls, API
charges, embeddings, reranking, or LangSmith traces.

## Alternatives and trade-offs

- PostgreSQL full-text search would reduce infrastructure, but Elasticsearch is
  locked for later BM25/vector/hybrid experiments.
- Post-filtering global results is simpler-looking but breaks both recall and
  isolation.
- One index per manuscript version could simplify atomic publication but creates
  more index lifecycle work; the current shared versioned index is sufficient for
  this baseline.
- Custom BM25 parameters were not tuned. Tuning against three documents and
  incomplete labels would overfit noise.

## Interview questions

1. How do TF, IDF, saturation, and length normalization influence BM25 ranking?
2. Why must tenant/version filters run before Top-K selection?
3. What is the difference between Recall@K and MRR?
4. How can incomplete relevance judgments create false retrieval failures?
5. Why is Elasticsearch derived state while PostgreSQL remains authoritative?
6. Why should BM25 parameters not be tuned against a tiny noisy fixture?
