# Runtime and Cache Storage Benchmark

## Hypothesis

Docker Compose should remain StoryGuard's reproducible application runtime, but
native execution may be justified for expensive local reranker experiments.
Docker named volumes may improve model loading compared with macOS bind mounts,
while warm inference should be largely independent of model-cache storage.

## Developer prediction

The developer expected Docker to be the more reliable and reproducible default
because it fixes the software environment. Native execution might be faster for
some experiments. The goal was to measure both and turn the result into an
explicit project rule.

Docker does not remove MacBook hardware effects: Docker Desktop still shares
the host CPU, RAM, SSD, and thermal limits. It isolates software dependencies,
not hardware variability.

## Compared runtimes

1. Docker backend with `.local/hf-cache` mounted from the project.
2. The same Docker image with an identically seeded temporary named volume.
3. Native project `.venv` with the same project-local model cache.

The named-volume seed time was excluded. An entirely empty Hugging Face cache
was not benchmarked because downloading 3.3 GB would measure network and Hub
authentication rather than StoryGuard runtime performance.

## Dataset and versions

- Dataset: `feyninc/gacha`
- Immutable dataset revision: `076b8b186236941df371a8d9b14be4cb4c7498fb`
- Selection: test shard 0 of 24, ten deterministic queries
- Embedding model: `google/embeddinggemma-300m@57c266a740f537b4dc058e1b0cda161fd15afa75`
- Reranker: `BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`
- Docker: aarch64, Python 3.14.4, Torch 2.12.1+cpu,
  Sentence Transformers 5.7.0, MPS unavailable
- Native: arm64, Python 3.14.4, Torch 2.12.1,
  Sentence Transformers 5.7.0, MPS unavailable

Raw ignored artifacts are stored at
`.local/experiments/runtime-storage-benchmark/summary.json`.

## Fresh-process model loading

Each value is the median of three new processes with filesystem caches left in
their normal warm state.

| Runtime / model cache | EmbeddingGemma | BGE reranker |
|---|---:|---:|
| Docker + bind mount | 3.164 s | 3.227 s |
| Docker + named volume | **2.984 s** | **3.049 s** |
| Native + bind mount | 3.382 s | 3.521 s |

The named volume improved process-cold model loading by about 5-6%. This is a
small one-time saving compared with reranker inference.

## Query latency

These medians exclude model loading. The full pipeline is Hybrid RRF Top-30
followed by cross-encoder reranking.

| Runtime / model cache | Hybrid median | Full pipeline median |
|---|---:|---:|
| Docker + bind mount | 155 ms | 51.13 s |
| Docker + named volume | **153 ms** | 51.46 s |
| Native + bind mount | 168 ms | **20.57 s** |

Total uncached compute for all ten queries, including both model loads, was:

| Runtime / model cache | Ten-query compute |
|---|---:|
| Docker + bind mount | 525.2 s |
| Docker + named volume | 528.9 s |
| Native + bind mount | **220.7 s** |

Named-volume storage did not improve warm inference. Native reranking was about
2.5 times faster than Docker in this run, although native hybrid retrieval was
slightly slower.

## Experiment-result cache

Repeating completed phases returned `already_complete`; neither model loading
nor inference ran.

| Runtime / storage | Candidate cache hit | Rerank cache hit |
|---|---:|---:|
| Docker + bind mount | 1.50 s | 0.77 s |
| Docker + named volume | 1.46 s | 0.78 s |
| Native + bind mount | **0.84 s** | **0.10 s** |

The Docker values include short-lived container startup. The native values are
direct process wall time.

## Quality and reproducibility

All three variants produced:

- the same ten query IDs;
- identical ordered Top-30 hybrid candidates for 10/10 queries;
- identical ordered reranker output for 10/10 queries;
- identical Top-10 output and relevant-evidence rank for 10/10 queries;
- Recall@1 0.80, Recall@5/10/20/30 1.00, and MRR@10 0.8833.

This ten-query subset validates equivalence between runtimes; it is too small
to replace the 233-query quality evaluation or define a production SLA.

## Failure analysis

The first Docker experiment attempts exposed two missing runtime inputs:

- the script needed `PYTHONPATH=/app`;
- benchmark fixtures needed the project `data` directory mounted read-only.

Both are now explicit in `compose.yaml`. Subsequent benchmark runs succeeded.
This illustrates the relevant reliability trade-off: Docker is reproducible
after every required input is declared, while native execution can silently
inherit paths and packages from the host.

Run order and MacBook thermal state were not randomized, so small differences
should be treated as noise. The approximately 2.5x reranker difference is much
larger than the storage differences, and native ran last under at least as much
prior load, but a target-hardware benchmark is still required for production
capacity planning.

## Cost and observability

- Paid API cost: zero
- LangSmith traces: none; no LLM calls occurred
- Temporary named-volume size: 3.4 GB; removed after the benchmark
- Persisted ignored raw results: 3.4 MB
- Elasticsearch was stopped after retrieval

## Developer conclusion

Allow native execution only for heavy reranker experiments. Keep the UI and
application runtime in Docker.

## Discussion and decision

The conclusion matches the measurements. Model-cache storage changed startup
by only 5-6%, while the Docker/native runtime changed reranker inference by
about 2.5x. Therefore:

1. Docker Compose is canonical for the UI, API, workers, integration tests, and
   normal experiments.
2. UI requests always reach the Docker backend/worker. Native Python is never
   an application-serving path.
3. Native execution is permitted only for resource-heavy local reranker
   experiments where Docker runtime makes iteration impractical.
4. A native exception must preserve pinned model/data revisions, fingerprinted
   artifacts, project-local ignored caches, and a small Docker equivalence
   check before its results are trusted.
5. Production latency and capacity decisions must use the target container and
   hardware, not native Mac timings.
6. Keep the project bind-mounted model cache. The small named-volume cold-load
   improvement does not justify hidden duplicated storage or harder cleanup.

