# Flash Lite pool promotion

## Hypothesis

Different Google model IDs have separate Free Tier limits. A second API model
under the stable entity-resolution alias could add usable capacity without
changing application routing. The risk was that a cheaper or open model would
reduce decision quality, structured-output reliability, or latency.

## Developer prediction

The developer expected Gemini API models, including API Gemma, to outperform the
local fallback and requested three or four load-balanced deployments. For API
Gemma 4, the developer selected 31B and allowed at most a two-percentage-point
regression from Gemini 3.5 Flash Lite in accuracy and JSON reliability.

Discussion corrected one assumption: provider family is not evidence of task
quality. Each concrete deployment needed the same fixed evaluation before it
could join the production alias. Multiple Google projects were excluded; this
experiment used different model IDs in one project.

## Baseline

Gemini 3.5 Flash Lite, experiment `gateway-v1-test-79d049d6`:

- model decision accuracy: 18/18 (100%);
- end-to-end accuracy: 18/19 (94.74%);
- first-pass valid output: 100%;
- provider errors and repairs: zero;
- p50/p95 latency: 0.844/1.423 seconds;
- paid-tier estimate: $0.005974 total, while the declared Free Tier cost was $0.

The baseline artifact is
`.local/experiments/gateway-v1-test-gemini35-lite.json`.

## Candidates

Experiment `gateway-v1-test-f8530f1e` evaluated:

- `gemini/gemini-3.1-flash-lite`, thinking disabled, 1,536 output tokens;
- `gemini/gemma-4-31b-it`, 1,536 output tokens.

Gemini 2.5 Flash Lite was also discovered and configured for a smoke, but its
strict-output request returned 404. It was removed before the full run rather
than retained as a dead deployment.

## Dataset and versions

- split: `test`, 19 fixed cases, 18 generated model comparisons per model;
- fixture SHA-256:
  `a6b2450da287efa8de326a369ede77c7a00e6340959499d32c193bfdb0b906f8`;
- prompt: `entity_resolver:v1`;
- prompt SHA-256:
  `50285d78190df977651593a1eaabd9b5a5cb82e7832c10347fe0ec6748e17d1e`;
- candidate routing SHA-256:
  `0f2777ef99ed175605216443a6156f00e2a8a0b031f9a5ca30551a6b0d430baa`;
- raw candidate artifact:
  `.local/experiments/gateway-v1-api-pool-candidates.json`.

The artifact's generic `thresholds` block still carries the original Lesson 6.1
gain/cost fields. The pool decision used the separately approved admission gate:
no more than two percentage points of accuracy regression and at least 98%
first-pass valid structured output.

## Metrics

| Metric | 3.5 Flash Lite | 3.1 Flash Lite | API Gemma 4 31B |
| --- | ---: | ---: | ---: |
| Model decision accuracy | 100% | 100% | 50% |
| End-to-end accuracy | 94.74% | 94.74% | 47.37% |
| First-pass valid output | 100% | 100% | 50% |
| Provider errors | 0/18 | 0/18 | 9/18 |
| Repairs | 0 | 0 | 0 |
| p50 latency | 0.844 s | 0.855 s | 19.633 s |
| p95 latency | 1.423 s | 1.690 s | 34.982 s |
| Paid-tier estimate | $0.005974 | $0.004351 | unavailable |

All nine successful API Gemma calls made the labeled decision, but nine other
calls returned provider 500 errors. Treating failed calls as incorrect is why
effective accuracy is 50%; conditional quality cannot compensate for 50%
availability.

## Failure analysis

API Gemma's initial strict-output smoke returned a provider 500 and its single
retry succeeded. The full evaluation nevertheless produced nine 500s. It failed
the reliability and latency gates and was removed from active routing. Gemini
3.1 Flash Lite produced no schema, evidence, provider, repair, or fallback
failure. The one end-to-end miss for every arm was the unchanged deterministic
candidate-generation miss, not a model decision.

## LangSmith IDs

Gemini 3.1 Flash Lite examples:

- `01a09b33-d168-75d0-b30d-171ff3f09633`;
- `01a09b33-ebba-7812-adc7-f07105d6064f`.

API Gemma 4 31B examples:

- `01a09b35-7599-78c0-a566-2399d093649e`;
- `01a09b35-e17e-7843-bce2-8890fe1375f5`.

The raw artifact retains all available per-case trace IDs and safe gateway
telemetry without API keys or manuscript excerpts in minimal trace mode.

## Developer conclusion and discussion

The developer promoted Gemini 3.1 Flash Lite alongside Gemini 3.5 Flash Lite
and rejected API Gemma 4 31B. This is supported by the fixed results: the two
Flash Lite models were equal on measured accuracy and structured output, while
API Gemma failed half its model calls and was much slower.

## Decision

`storyguard-entity-resolution` now has two production deployments:

- `sg-resolution-prod-gemini35-lite-v1`;
- `sg-resolution-prod-gemini31-lite-v1`.

LiteLLM uses its default simple-shuffle routing between them. Four production
strict-JSON smoke requests reached both deployments (three 3.5, one 3.1), all
successfully. This small smoke proves reachability, not statistical fairness.
The existing local `gemma4:e4b` alias remains the only provider fallback. No API
Gemma deployment, Gemini 2.5 deployment, extra API key, or extra Google project
was promoted.
