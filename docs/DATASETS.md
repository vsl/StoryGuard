# StoryGuard Data Strategy

StoryGuard uses real narrative data instead of requiring the developer to write complete fake novels.

## Dataset roles

### Public-domain manuscripts

Hugging Face: `common-pile/project_gutenberg`

Use for manuscript ingestion, chunking, Story Bible extraction, RAG demos, and source material for controlled continuity mutations. Use a small pinned subset for local development.

### Story QA

Hugging Face: `meithnav/narrativeqa`

Use for factual/multi-hop QA, answer correctness, citations/evidence, and StoryGuard-owned no-answer variants.

### Retrieval evaluation

Hugging Face: `illuin-conteb/narrative-qa`

Use for query-to-relevant-chunk evaluation, Recall@K/MRR, BM25/vector/hybrid/reranker comparisons, query rewriting, and HyDE experiments.

### Continuity evaluation

Generate controlled mutations over selected public-domain narratives. Include both true contradictions and negative controls.

## Reproducibility

Create `config/datasets.yaml` and pin dataset ID, revision, split, selected row/document IDs, filters, transformation version, and license/provenance notes. Never let an eval silently change because a remote dataset changed.

## Hugging Face model lifecycle

Use `datasets` and `huggingface_hub`. Pin model revisions for local embeddings/rerankers used in benchmarks and record repository, revision, license, family, and dimension where relevant.

## Fine-tuning

Not part of StoryGuard v1. Datasets are for development, retrieval, evaluation, controlled mutation, and demos.
