# StoryGuard Dataset Strategy

StoryGuard uses real narrative data instead of requiring the developer to write entire books.

## Public-domain manuscripts

Hugging Face:

```text
common-pile/project_gutenberg
```

Use for:
- manuscript ingestion;
- chunking;
- Story Bible extraction;
- long-document RAG;
- controlled continuity mutations.

Use only an intentionally small pinned development subset.

## Story QA

Hugging Face:

```text
meithnav/narrativeqa
```

Use for:
- factual QA;
- multi-hop QA;
- answer correctness;
- evidence/citation eval fixtures.

## Retrieval benchmark

Hugging Face:

```text
feyninc/gacha
```

Use for:
- BM25/vector/hybrid/reranker comparison;
- Recall@K;
- MRR;
- query rewriting;
- HyDE experiments.

Pin revision `076b8b186236941df371a8d9b14be4cb4c7498fb` and use the
`corpus/train` and `questions/train` configurations. The local fixture contains
ten selected public-domain narrative books: two development books and eight
held-out test books.

Ground truth is never a supplied chunk ID. For each question, locate the exact
`chunk-must-contain` evidence in its corresponding full book, run StoryGuard's
normal parser, and label every resulting overlapping chunk containing that
evidence as relevant. Retrieval remains scoped to that book's deterministic
project and manuscript version.

Gacha is licensed CC BY-NC-SA 4.0. StoryGuard uses it only for this
non-commercial project, preserves provenance, and does not assume that a work's
US public-domain status applies in every territory.

## Continuity

Create controlled mutations from selected public-domain narratives.

Include both:
- actual contradictions;
- negative controls / non-conflicts.

## Reproducibility

Pin:
- dataset ID;
- revision;
- split;
- selected row/document IDs;
- transformation version;
- license/provenance metadata.
