# LangSmith Tracing

## Mental model

A trace is the complete retrieval request. Spans are the timed operations inside
it. The tree preserves parent/child relationships and makes latency ownership
visible:

```text
retrieve_hybrid_reranked
  -> retrieve_hybrid
       -> retrieve_bm25 ----+
       -> retrieve_vector --+  concurrent
       -> rrf_fusion
  -> reranker
```

Parallel latency follows the slower branch rather than the sum of both branches.
Tracing explains what ran and where time was spent; it does not prove that a
ranking is correct.

## StoryGuard implementation

`backend/app/ai/tracing.py` wraps LangSmith `traceable` with StoryGuard privacy
processors. `backend/app/ai/retrieval.py` traces BM25, vector retrieval, hybrid
retrieval, RRF, and the two root workflows. `backend/app/ai/reranking.py` traces
the local cross-encoder. The search endpoint exposes `rerank=true|false`, and
the UI checkbox sends that choice through the real API.

With reranking enabled, the root trace is `retrieve_hybrid_reranked` and includes
the `reranker` span. Without it, the root is `retrieve_hybrid` and the reranker
span is absent. Project and current-ready-manuscript-version scope is enforced
before retrieval.

The Next.js rewrite proxy uses `experimental.proxyTimeout: 120_000`. Its default
30-second timeout terminated valid local reranker requests before the backend
finished. A live request taking 62.7 seconds returned HTTP 200 after this fix.

## Trace privacy modes

- `minimal`: hashed safe IDs, durations, counts, rankings/scores, strategy,
  model metadata, and errors; no query or manuscript text.
- `redacted`: the same diagnostics plus placeholders containing only string
  lengths; no raw query or chunk text.
- `full`: raw inputs and outputs, including queries and manuscript chunks.

`full` requires explicit opt-in because manuscripts may be unpublished and
confidential. `LANGSMITH_TRACING=false` disables external traces. Docker
containers must be recreated, not merely restarted, after these environment
values change.

## Developer checkpoint

For the same manuscript search, the developer observed:

| Span | `rerank=true` | `rerank=false` |
|---|---:|---:|
| BM25 | 0.08 s | 0.16 s |
| Vector | 0.14 s | 6.09 s |
| RRF | 0.00 s | 0.00 s |
| Reranker | 50.15 s | absent |

The reranked trace showed hybrid retrieval finishing in about 0.14 seconds,
consistent with concurrent BM25/vector execution. The reranker owned almost all
of the 50-second latency and changed result order. The non-reranked vector time
came from a different runtime state and should not be treated as a controlled
latency comparison.

The changed order proves that the reranker affected ranking, not that the new
order is better. Quality still requires labeled metrics and failure inspection.

Verified example traces:

- reranked: `01a0438c-ca6f-7461-8fb6-ad096388c045`
- hybrid only: `01a0438c-ca44-7270-bbe3-ce29010e115a`

## Failure diagnosis

```text
no trace
  -> verify LANGSMITH_TRACING inside the running container
  -> verify API key/project/endpoint without logging the key
  -> recreate backend and worker after .env changes

trace ends around 30 seconds with frontend 500
  -> inspect the Next.js rewrite proxy

slow trace
  -> find the dominant child span
  -> retrieval span: inspect embeddings/Elasticsearch
  -> reranker span: inspect model load, hardware, and candidate count
```

An empty result can still produce a successful trace. User-safe API errors stay
generic while detailed failures remain in backend logs and LangSmith metadata.

## Tests and operational checks

- Backend suite: 34 passed, 9 skipped.
- Real application API integration: 2 passed.
- Frontend suite: 5 passed; lint and production build passed.
- Docker services were healthy and live searches produced both trace shapes.
- Minimal-mode traces were checked for absence of raw query/manuscript text.
- `rerank=false` was checked for absence of a reranker span.

Tracing has no paid model-token cost here, but LangSmith storage/retention and
privacy remain operational costs. Instrumentation overhead is small compared
with the observed local cross-encoder latency.

## Alternatives and exclusions

- A custom tracing framework was unnecessary; LangSmith `traceable` plus input
  and output processors covers the workflow.
- Raw content is not the default because diagnostic convenience does not justify
  leaking confidential manuscripts.
- A relevance threshold or abstention rule was not added. Retrieval ranking and
  no-answer behavior require a separate evaluated change.
- The reranker was not moved to a background job in this lesson; the bounded
  two-minute proxy timeout supports the current explicit quality mode.

## Interview questions

1. Why does hybrid latency follow the slower parallel branch rather than the
   sum of BM25 and vector latency?
2. What does the presence of a reranker span prove, and what does it not prove?
3. Which data is safe in `minimal`, `redacted`, and `full` modes?
4. How would you diagnose a trace whose reranker dominates total latency?
5. Why must Docker containers be recreated after changing tracing environment
   variables?

