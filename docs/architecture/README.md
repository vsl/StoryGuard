# Architecture and engineering guide

This guide explains **what StoryGuard currently implements, how it works, and why the choices matter**. It is separate from the course instructions and chronological learning notes.

Implementation snapshot: **2026-09-16**. Code and active configuration take precedence over older design documents. The course cursor is Lesson **7.1: Grounded Story QA — not started**. This guide does not mark lessons complete or promote models.

## Choose a reading path

| Reader | Suggested path |
| --- | --- |
| GitHub visitor, 5 minutes | [System overview](system-overview.md) → [model inventory](models-and-gateway.md#model-inventory) → [measured results](evaluation-and-observability.md#recorded-results) |
| Interview preparation, 30 minutes | Overview → [search](embeddings-and-search.md) → [model gateway](models-and-gateway.md) → [interview guide](interview-guide.md) |
| Developer learning the implementation | Read the pages below in order, following their source-code links |

## Contents

1. [System overview](system-overview.md): capabilities, architecture, and technology choices.
2. [Application and storage](application-and-storage.md): HTTP requests, background jobs, databases, and trust boundaries.
3. [Manuscript ingestion](manuscript-ingestion.md): upload, parsing, chunking, indexing, and version promotion.
4. [Embeddings and search](embeddings-and-search.md): lexical and semantic retrieval, fusion, and reranking.
5. [Entity extraction and resolution](entity-extraction-and-resolution.md): detect mentions, classify their type, and resolve identity.
6. [Structured story memory](structured-story-memory.md): facts, events, relationships, and evidence.
7. [Models and LiteLLM](models-and-gateway.md): specialist models, LLM aliases, deployment pools, retries, and fallback.
8. [Evaluation and observability](evaluation-and-observability.md): datasets, experiments, metrics, traces, and diagnosis.
9. [Interview guide](interview-guide.md): concise explanations and questions with suggested answers.

## One example throughout

The following **synthetic teaching manuscript** is used across this guide. It is not a test run, benchmark fixture, or observed model output. Short IDs such as `entity-mara` and `evidence-1` are explanatory placeholders; the application issues real IDs.

```markdown
# Chapter 1

Mara Vale wore a blue coat. Mara entered North Hall in Porto.
On June 1, 2023, Mara Vale and Ilya Reed married in Porto.

# Chapter 2

On March 2, 2024, Mara Vale and Ilya Reed divorced in Porto.
```

We follow this text from an uploaded file to searchable chunks, named mentions, resolved entities, and event-backed relationships. A real model can miss or misinterpret any of these records.

## Vocabulary

| Term | Meaning in StoryGuard |
| --- | --- |
| Manuscript version | One uploaded source file and its derived data; current becomes visible only after successful ingestion |
| Chunk | A bounded span of parsed chapter text used for indexing and extraction |
| Embedding / bi-encoder | A model encodes each text independently into a reusable numerical vector |
| BM25 | Lexical relevance scoring over Elasticsearch's text index |
| kNN | Retrieval of nearby vectors; here, approximate cosine search in Elasticsearch |
| RRF | Reciprocal Rank Fusion: combine ranked lists using positions rather than raw scores |
| Cross-encoder | A model reads a query and candidate passage together to score relevance |
| Mention / entity | A written occurrence such as “Mara” / the resolved identity to which occurrences belong |
| Coreference | Predicting which text spans refer to the same entity |
| Evidence | A server-identified source passage with version and character offsets |
| Model alias / deployment | An application-facing capability name / a concrete provider-model target |
| Output repair / fallback | Another request to fix invalid output / routing to another model group after provider failure |
| RAG | Retrieval-augmented generation; retrieval is implemented, grounded QA generation is upcoming |
| Coverage / recall | Successfully processed chunks / how much labeled relevant information was recovered |

## How to read the evidence

- **Implemented** means reachable code exists, not that every input has been proven correct.
- **Selectable** means an explicit user/configuration choice, not automatic model routing.
- **Historical result** means a previously recorded run with its own model, prompt, labels, hardware, and dataset.
- **Planned** means a course/specification target, not a working endpoint.

The [specifications](../specs/storyguard_backend_ai_spec.md) describe a broader target. [Learning notes](../learning/README.md) preserve completed discussions; [experiment reports](../experiments/README.md) preserve measured decisions. Some older summaries reference Lesson 6.1 or earlier defaults; consult [course progress](../../COURSE_PROGRESS.md) and the source links here for current state.

## Maintaining this guide

Update the affected page when changing a workflow, model alias, API default, or storage contract. Keep experiment numbers attached to the original reports rather than rewriting historical results as new measurements.

Mermaid blocks in these Markdown pages are the editable diagram sources. The three shareable SVG exports are [system architecture](diagrams/system-overview.svg), [search](diagrams/embeddings-and-search.svg), and [model routing](diagrams/models-and-gateway.svg). Re-export them when their source block changes; do not edit the SVG labels independently. Rendering details and verification scope are in [documentation verification](verification.md).
