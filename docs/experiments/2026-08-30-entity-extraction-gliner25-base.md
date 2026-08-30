# GLiNER2.5 Base Entity Extraction Candidate

## Experiment metadata

```text
experiment_id: entity-extraction-gliner25-base-v1-20260830
status: retained as a future fast-tier candidate; not promoted as default
baseline: gemma4:e4b through LiteLLM with entity_extractor:v2
candidate: fastino/gliner2.5-base-v1 on CPU
primary_split: frozen model test fixture
```

## Hypothesis

GLiNER2.5 Base may reduce local extraction latency and remove generative schema
failures, but it must not replace Gemma unless entity quality also improves on
the same frozen fixture.

## Developer prediction

The developer predicted that GLiNER2.5 Base would not improve the result over
Gemma, but wanted measured evidence before deciding whether it had any useful
role in StoryGuard.

## Baseline

- model: `gemma4:e4b`
- Ollama digest: `c6eb396dbd59`
- LiteLLM alias: `storyguard-entity-gemma4-e4b`
- prompt: `entity_extractor:v2`
- prompt SHA-256:
  `e722e386609ec27ffdcac818b867e5d3272fe9c08985bbb40a309ccc5aa60aff`
- temperature: `0`
- structured JSON output with one bounded repair

## Candidate

- package: `gliner2==2.0.0`
- checkpoint: `fastino/gliner2.5-base-v1`
- immutable revision:
  `72ac19b486cd4557424c8d61114e7530c243e9b0`
- architecture: boundary extractor
- device: CPU
- threshold: `0.5`
- labels: `character`, `location`, `object`, `organization`, `other`
- label descriptions: none
- direct half-open source spans with server-side evidence validation

GLiNER is an encoder extractor, not a LiteLLM model. It was therefore tested
through a separate experiment runner and was not added to the production LLM
routing path.

## Dataset and reproducibility

- fixture: `data/datasets/fixtures/entity_extraction_model_eval.jsonl`
- examples: 24
- gold mentions: 54
- split: test
- fixture SHA-256:
  `5184888d7db6164ee8c1137c1ebf5d95f905abe8c0e5345fa29e436a744b24eb`
- model registry SHA-256:
  `203bf791e845220260f47002923b16cf0c22d9ba3fdf026cdd0ad33902faab46`

Both runs used the same fixture order and exact-span/type scoring. No prompt
examples, label descriptions, threshold tuning, or test-set-specific rules
were added for GLiNER.

## Quality metrics

| Metric | Gemma V2 | GLiNER2.5 Base |
|---|---:|---:|
| Predicted mentions | 54 | 57 |
| Precision | **0.9444** | 0.7368 |
| Recall | **0.9444** | 0.7778 |
| F1 | **0.9444** | 0.7568 |
| Type accuracy on matching boundaries | **0.9444** | 0.9130 |
| Character recall | **1.0000** | 0.8636 |
| Location recall | **1.0000** | 0.9333 |
| Object recall | **1.0000** | 0.6667 |
| Organization recall | **1.0000** | 0.8000 |
| Other recall | **0.5000** | 0.1667 |
| Invalid span rate | 0 | 0 |
| Failed examples | 0 | 0 |
| Repairs | 1 | **0** |

Gemma produced 51 exact true positives. GLiNER produced 42 exact true
positives, 15 non-true-positive predictions, and missed 12 gold mentions.
Gemma had three failing examples; GLiNER had 17.

## Latency, memory, and cost

| Metric | Gemma V2 | GLiNER2.5 Base |
|---|---:|---:|
| Process/model cold start | 11.795 s | 5.714 s |
| Steady p50 per example | 10,666.5 ms | **38.3 ms** |
| Steady p95 per example | 15,066.6 ms | **42.6 ms** |
| Registered artifact size | 9.6 GB | **407 MB** |
| Paid API cost | $0 | $0 |

GLiNER was about 278 times faster at p50 and 353 times faster at p95. Its
repeat-run peak RSS was 2.26 GB, an increase of 1.78 GB in the native process.
Gemma memory was owned by the external Ollama process and was not measured, so
RAM usage is not directly comparable.

The first successful GLiNER run after dependency setup reported a 19.48-second
load plus first inference; the immediate repeat reported 5.71 seconds. Warm
filesystem and process state make the cold-start number noisy. The steady
per-example latency and unchanged quality metrics were stable across both runs.

## Failure analysis

GLiNER's main failure modes were:

- generic roles and common nouns extracted as named entities, including a
  ranger, an empress, a harbor, a road, a plaque, and a scroll;
- named animal characters missed;
- named events, laws, prophecies, and concepts missed, leaving `other` recall
  at 1/6;
- organization-to-object, location-to-object, and character-to-object type
  confusion;
- incomplete boundaries such as extracting only the leading word of a named
  object.

Quoted manuscript instructions were not executed. GLiNER still extracted
common nouns inside or near those passages, so an encoder architecture removes
instruction-following risk but does not remove false-positive noise. All
accepted predictions passed `text[start:end] == surface_text` validation.

Gemma's only three exact-match failures were named events or concepts labeled
`object` instead of `other`. It found every gold character, location, object,
and organization.

The initial GLiNER load failed before inference because the official tokenizer
compatibility path required `protobuf`, which was not declared by the
`gliner2[local]` extra. StoryGuard now pins `protobuf==7.36.0`. The subsequent
native run and Python 3.14 Docker build succeeded. DeBERTa also logged a safe
fallback from unsupported SDPA attention to eager attention.

## Tests and observability

- focused entity extraction tests: 10 passed;
- full backend suite: 49 passed, 12 skipped;
- dependency check: no broken requirements;
- backend and worker Docker images: built successfully;
- recreated backend: healthy;
- recreated worker: running;
- GLiNER/protobuf import inside worker: `2.0.0` / `7.36.0`;
- LangSmith trace IDs: none; tracing was disabled or unavailable;
- API cost: zero.

## Developer conclusion

Retain GLiNER2.5 Base only as a future fast-tier candidate, not as the default
entity extractor.

## Discussion and decision

The conclusion matches the measurements. GLiNER has a strong operational
advantage but a large quality regression, especially for StoryGuard's
recall-first objective and custom `other` category.

1. Keep `gemma4:e4b` as the only default entity extraction model.
2. Do not connect GLiNER to the production extraction path or LiteLLM.
3. Keep the pinned GLiNER entry and reproducible runner as an offline
   fast-tier candidate.
4. Do not tune its threshold or label descriptions in this experiment because
   either change would introduce another variable.
5. Reconsider a fast tier only when StoryGuard has a concrete latency or
   throughput requirement. Any routing policy, threshold tuning, label
   descriptions, or cascaded GLiNER-to-Gemma design requires a separate
   approved experiment.

## Follow-up: explicit upload choice

After observing a 38-minute full-manuscript ingestion job, the developer
explicitly requested GLiNER2.5 Base as a selectable development extractor,
alongside Gemma and Qwen3.5 9B. This supersedes the offline-only restriction
above, not the default-model decision: Gemma remains the default. The same
pinned GLiNER revision, labels and threshold are reused without tuning or
automatic routing. Upload stores the chosen extractor on the manuscript
version; UI copy communicates the measured recall trade-off. This integration
does not establish a new quality ranking on full manuscripts.
