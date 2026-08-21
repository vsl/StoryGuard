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
illuin-conteb/narrative-qa
```

Use for:
- BM25/vector/hybrid/reranker comparison;
- Recall@K;
- MRR;
- query rewriting;
- HyDE experiments.

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
