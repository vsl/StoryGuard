# Parsing, Chapters, Scenes, and Chunking

## Mental model

```text
original bytes -> deterministic blocks -> chapters -> scenes -> chunks

lines      identify structural boundaries
characters identify scene/chunk spans inside chapter.text
tokens     control chunk size and overlap
```

Parser precision and recall measure detected structural boundaries. They are not
RAG metrics. Retrieval Recall@K measures whether relevant evidence appears in the
first K search results and requires a retriever plus labeled queries.

## StoryGuard implementation

- `backend/app/manuscripts.py` validates `.txt`, `.md`, and `.docx` uploads,
  computes the original-file SHA-256, and stores bytes in MinIO under
  `projects/{project_id}/manuscripts/{version_id}/original.<ext>`.
- `backend/app/parsing.py` normalizes blocks, detects structure, creates
  chapter-relative character offsets, hashes normalized text, and chunks with
  target/max/overlap `700/900/100` regex tokens.
- `backend/app/queue/tasks/ingestion.py` downloads the version-scoped object,
  parses it off the event loop, replaces prior parsed rows atomically, and marks
  the job completed or failed.
- PostgreSQL stores metadata in `manuscript_versions` and `job_runs`, normalized
  content in `chapters`, `scenes`, and `chunks`, and parser diagnostics in
  `manuscript_versions.parse_metadata`.

The upload helper and worker task exist, but the HTTP upload/job producer endpoint
is not yet wired. Elasticsearch indexing and embeddings are also future stages.

## Detection rules

- Markdown headings define chapters in `.md`.
- DOCX heading styles define chapters; conservative regex is the fallback when
  heading styles are absent. DOCX ZIP size and entry-count checks defend against
  malformed or expanding archives.
- TXT recognizes `Chapter N`, prologue, epilogue, sequential standalone numbers,
  and sequential Roman-numbered titled headings.
- Bare numeric/Roman sequences need at least three headings and at least 200
  narrative characters between adjacent candidates. This rejects compact lists
  but intentionally misses a two-chapter book using only bare numbers.
- Explicit `***`, `* * *`, and `---` split scenes. Standalone `#` additionally
  splits TXT scenes, but not Markdown. Front-matter markers do not create scenes.
- When no reliable heading exists, all readable text becomes one fallback chapter
  with a warning. This preserves content instead of asking an LLM to invent
  structure.

## Data and evidence lineage

```text
manuscript_version
  -> chapter
    -> scene
      -> chunk
```

Every chunk references its manuscript version, chapter, and optional scene.
Scene and chunk offsets slice `chapter.text`, not the raw file and not token
positions:

```python
chapter.text[chunk.start_offset:chunk.end_offset] == chunk.text
```

The original bytes remain in MinIO. Exact detected TXT/Markdown chapter and scene
lines are recorded as 1-based normalized line numbers in parse metadata. Exact
raw-file byte offsets are not currently stored, so a future click-through to the
original may require a source-span design or deterministic re-alignment.

Content hashes detect unexpected normalized-text changes. The manuscript version
scope prevents evidence from silently crossing projects or versions. Uploaded
manuscript text is treated as untrusted data and never executed.

## Experiments and decisions

Parser v2 was measured on Alice, Treasure Island, Sherlock Holmes, and Little
Brother using SHA-bound exact line labels:

- chapter boundary F1: `59.65% -> 100%`;
- scene boundary F1: `0% -> 100%`;
- fallback documents: `2/4 -> 0/4`;
- candidate false/missing exact lines: `0/0`;
- chunks: `670 -> 707` (`+5.52%`).

The result proves correctness only for the labeled data and negative controls.
The developer promoted v2 while explicitly retaining that limitation. An initial
count-based evaluator was rejected because equal counts can hide misplaced
boundaries; the promoted evaluation compares exact line positions.

The overlap experiment was rerun after parser promotion:

- `overlap=0`: 381 chunks, 251,391 estimated embedding tokens, 0/321 boundary
  probes covered;
- `overlap=100`: 424 chunks, 287,991 estimated embedding tokens, all 321 probes
  covered, 14.56% duplicate-token ratio.

Overlap 100 remains provisional. Its real retrieval value must be decided later
using Recall@K, MRR, Top-K diversity, and embedding/index cost.

## Alternatives and failure cases

An LLM parser could recognize unusual headings but adds latency, token cost,
nondeterminism, prompt-injection exposure, and unsupported inferred boundaries.
StoryGuard v1 therefore uses deterministic parsing and expands rules only against
observed labeled failures.

Known limitations include unknown publisher layouts, ambiguous short numeric
structures, missing raw-source byte spans, and limited scene-style diversity.
Parser errors fail the job closed and do not publish partial chapter/scene/chunk
rows. Reprocessing deletes and atomically replaces rows for the same manuscript
version; project/version scope is checked before and after parsing.

No LLM, LangSmith trace, embedding, Elasticsearch query, or API charge was
involved in this lesson. Local single-run timings were too noisy to use as a
selection metric.

## Interview questions

1. Why are parser boundary precision/recall different from retrieval Recall@K?
2. Why must offsets specify their coordinate system?
3. Why does overlap improve boundary context while increasing embedding volume?
4. How does one-chapter fallback preserve evidence better than guessing?
5. Why should exact-position labels be bound to a source hash?
6. What are the trade-offs between deterministic parsing and LLM structure
   inference?
