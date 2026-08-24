# Chunk Overlap Baseline

## Decision

Use `overlap_tokens=100` as the provisional StoryGuard baseline. Re-evaluate it
with Recall@K, MRR, retrieval-result diversity, and embedding/index cost after the
BM25 baseline exists.

The developer predicted better boundary context with more duplicate data. The
experiment confirmed that structural trade-off, but it did not measure retrieval
or answer accuracy.

## Fixed input

- dataset: `public_domain_manuscripts`;
- pinned Gutenberg IDs: `11`, `120`, `1661`;
- fixture manifest SHA-256:
  `d8cce63201cf829a7d7bf9564e288cf6363a047b9a22dd042bc51ebdc0f5bb6a`;
- parser: promoted `v2`;
- tokenizer: `regex-v1`;
- target/max tokens: `700/900`.

## Compared configurations

```text
baseline  overlap=0
candidate overlap=100
```

## Results

| Metric | Baseline | Candidate |
|---|---:|---:|
| Boundary probe coverage | 0 / 321 (0%) | 321 / 321 (100%) |
| Chunks | 381 | 424 |
| Estimated embedding tokens | 251,391 | 287,991 |
| Duplicate token ratio | 0% | 14.56% |
| Chapter-detection fallback documents | 0 / 3 | 0 / 3 |
| Invariant failures | 0 | 0 |

Observed medians were about 47 ms for baseline and 28 ms for candidate in this
single local run. The difference is noisy and not interpreted as a speed gain.

## Failure categories and limitations

- The 80-token probes are centered on baseline chunk boundaries. They measure
  whether local boundary context survives, not whether a retriever finds it.
- Parser v2 recognizes the numbered `Treasure Island` headings and Roman-numbered
  titled `Sherlock Holmes` headings, so neither is a fallback in this rerun.
- No embeddings, Elasticsearch retrieval, LLM, LangSmith trace, API charge,
  Recall@K, MRR, answer accuracy, or Top-K diversity measurement was involved.

## Follow-up

During the BM25 lesson, run both overlap configurations against the same pinned
retrieval cases. Keep `100` only if its Recall@K/MRR or boundary-query gains
justify the extra 14.56% estimated embedding/index volume and do not cause harmful
Top-K duplication.
