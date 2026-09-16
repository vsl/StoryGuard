# Interview guide

[Guide index](README.md) · Previous: [Evaluation and observability](evaluation-and-observability.md)

These suggested explanations are grounded in the current repository. Adapt them to your own understanding. Historical numbers should always travel with their dataset size and limitations.

## A 60-second project introduction

> StoryGuard is my local AI engineering portfolio project for working with manuscripts. It ingests versioned documents, searches them with hybrid lexical and vector retrieval, and builds an evidence-linked Story Bible with entities, facts, events, and relationships. The frontend is Next.js; FastAPI serves requests; Taskiq and RabbitMQ run long jobs. PostgreSQL owns application state, MinIO keeps original files, and Elasticsearch stores text and vectors. I use specialist pretrained models for embeddings, reranking, extraction, and coreference, and route generative calls through LiteLLM. I compare model changes with fixed evaluations and inspect execution with LangSmith. Grounded question answering and continuity review are the next stages, rather than capabilities I claim are already finished.

## A five-minute architecture walkthrough

1. **Start with data ownership.** Show the [architecture image](diagrams/system-overview.svg). Explain why original files, durable state, and a derived index live in different stores.
2. **Follow one upload.** The API validates and versions the file, returns a job ID, and the worker parses, embeds, indexes, and extracts. The current pointer advances only when the version is ready.
3. **Follow one search.** Show the [search image](diagrams/embeddings-and-search.svg): current-version filters, concurrent BM25/vector candidates, RRF, optional cross-encoder stage, and source-linked top-ten passages. Mention that the option is currently enabled by default.
4. **Explain identity and memory.** Extraction finds names/types; resolution groups identities; memory extracts facts/events/relationships. Each can fail differently, and citation validity does not guarantee semantic truth.
5. **Explain model choice with evidence.** Show the [gateway image](diagrams/models-and-gateway.svg), one successful trade-off, and one rejected or risky candidate. Finish with current limitations.

## Questions and suggested answers

### Why Elasticsearch instead of a separate vector database?

The existing index supports both BM25 text search and dense vectors, so both branches share chunk IDs and scope metadata. That avoids another storage system just for vectors. PostgreSQL still owns application state. This is a practical project choice, not a claim that Elasticsearch is always the best vector database.

### Why combine BM25 with embeddings?

BM25 is useful for exact names and wording; embeddings help with semantic similarity. Their mistakes can be complementary. On the recorded held-out split, hybrid improved Recall@10 from 0.8734 to 0.9056 versus BM25, but some individual queries regressed. [Evidence](../experiments/2026-08-25-hybrid-rrf.md)

### Why RRF rather than adding the two scores?

The raw score scales differ. RRF combines rank positions using `sum(1 / (60 + rank))`, deduplicating by chunk ID. It avoids choosing a raw-score normalization scheme, though its fixed settings still need evaluation.

### What is the difference between embedding retrieval and reranking?

Embedding retrieval compares independently encoded vectors and reuses document embeddings. The cross-encoder jointly reads each query/passage pair, which is slower but can improve ordering. It only sees the retrieved candidate set. If the correct passage is absent from the top 30, reranking cannot recover it.

### Was the reranker worth its latency?

In the recorded 233-query evaluation, MRR@10 improved from 0.7126 to 0.8544 while median local latency increased from 147 ms to 10,917 ms. The lesson retained it as a selectable quality mode. The current API/UI starts with it enabled, and users can turn it off. I would measure the target environment before making a latency claim. [Evidence](../learning/cross-encoder-reranking.md)

### Did you train your own models?

No. This implementation uses pretrained models and custom application logic: prompts, schemas, source validation, routing, jobs, evaluation, and persistence. GLiNER and xCoRe are specialist components; Gemma and Gemini are prompted general-purpose models. A small isolated LoRA experiment is planned after the core, not deployed.

### Where does classification happen?

Entity type classification is part of the mention extractor's output: character, facility, GPE, location, organization, or vehicle. Resolution produces a constrained merge/separate/review decision. Structured memory assigns controlled fact/event/relation types. There is no standalone classification microservice or dedicated relationship model.

### Why keep both a small extractor and an LLM?

They expose a measurable speed/quality choice. In an older 24-example fixture, GLiNER was far faster but had lower exact-span/type F1 than Gemma. Gemma remains the upload default; GLiNER is an explicit development alternative. The result used older labels, so it is not current six-category quality evidence or an automatic routing policy. [Evidence](../experiments/2026-08-30-entity-extraction-gliner25-base.md)

### How do you resolve aliases without merging everyone with similar names?

Names only generate bounded candidates. Exact aligned xCoRe links can shortcut a pair; otherwise the configured LLM compares both mentions with evidence. Conflict checks preserve keep-separate constraints, and decisions are audited. These guards do not eliminate wrong merges. Candidate generation itself can miss distant aliases.

### What is a decision you would discuss critically?

The coreference shortcut was promoted for speed despite a five-case diagnostic showing accuracy fall from 80% to 60%. The single skipped LLM call was an incorrect shortcut in that diagnostic. This is an accepted, visible risk needing broader evidence, not an accuracy improvement. [Evidence](../experiments/2026-08-31-coreference-gemma-promotion.md)

### How does LiteLLM load balancing differ from fallback?

Two Gemini deployments share the resolution alias, so simple-shuffle can select either during normal operation. Local Gemma has a different alias used as the provider fallback. Output repair is a third concept: a schema/evidence-invalid response gets one more application request through the original pool alias. The actual deployment ID is recorded because the alias alone does not identify the serving model.

### How do you avoid infinite retries?

Each layer is bounded. The resolution gateway has a transient provider retry budget and one fallback group. Invalid output gets one repair. A persisted retryable pair error gets at most one later job attempt. Candidate counts, batch work, per-call timeouts, and coreference scans also have limits. A short retry sleep is not a durable timer, so a crash can require Resume.

### How do you prevent hallucinations?

I would say “mitigate and expose,” not “prevent completely.” Models get untrusted manuscript data and server-issued evidence IDs. Code checks schemas, spans, scope, allowed IDs, and supported relationship/event structure; invalid outputs are repaired or omitted. A real citation can still be misinterpreted. General grounded-answer verification is upcoming.

### Why not answer every question only from the Story Bible?

Extracted memory is incomplete and can fail. A missing marriage record does not prove no marriage occurred. Search operates on manuscript chunks independently of complete memory, and future QA must retrieve source text when structured records are missing.

### How does a failed rebuild avoid making data worse?

Memory runs are pinned to version, prompt, and resolution-state fingerprint. The worker rejects stale scope and checks that a replacement's successful chunk set preserves prior coverage. Read APIs select a compatible completed run. This protects processing coverage; it does not prove better semantic extraction quality.

### What would you look at in LangSmith?

For slow search, inspect query embedding/vector retrieval, BM25, fusion, and reranking durations. For resolution, correlate job/batch IDs, actual deployment IDs, provider failures, repairs, and applied decisions. Minimal mode omits raw text on the instrumented paths. Traces supplement database audit records.

### How do you prove the UI really uses the backend?

Mocked contract tests are useful but insufficient. The repository also contains real-flow browser tests and historical smokes that reached APIs, PostgreSQL/MinIO, the queue, worker, and models without application-route interception. Distinguish those runs from unit tests and never present historical results as a new run. [Integration history](../frontend-api-gaps.md)

### What would need work before this became a hosted product?

Authentication/authorization, deployment security, resource limits, recovery, cleanup, and broader quality/reliability evidence would need deliberate design and verification. Local Compose is not cloud experience or high availability. These are limitations to acknowledge, not systems to claim as built.

## Claims to keep precise

| Avoid saying | Say instead |
| --- | --- |
| “I built a finished RAG chatbot.” | “I built hybrid retrieval and evidence-linked memory; grounded QA is next.” |
| “All AI calls use the gateway.” | “Generative calls use LiteLLM; specialist models run locally outside it.” |
| “The model was 100% accurate.” | “It made 18/18 correct generated-pair decisions on a fixed small test; one upstream miss remained.” |
| “Valid citations prove the answer.” | “They prove a reference is permitted; semantic support still needs checking.” |
| “Local inference is free.” | “That path has no paid API charges, but hardware, memory, and latency costs remain.” |
| “The queue guarantees exactly once.” | “Workers use persisted guards and bounded retries; cross-store operations are not one transaction.” |

## Practice checkpoint

Using only the three exported diagrams, explain what happens from uploading the teaching manuscript to searching for the wedding and viewing an ended relationship. For each model call, identify its input, serving location, output validator, and one failure mode. Compare your explanation with the workflow pages.
