# Model Gateway and Trade-offs

## Mental model

Application routing selects a stable capability alias. Deployment routing maps
that alias to concrete providers and models:

```text
entity resolution code
  -> storyguard-entity-resolution
  -> LiteLLM load-balanced pool
       -> Gemini 3.5 Flash Lite
       -> Gemini 3.1 Flash Lite
  -> transient failure: one model-group provider retry
  -> local Gemma 4 fallback
  -> both fail: persist failure, wait 5 seconds, one later job attempt
  -> second failure: terminal pair error
```

Invalid structured output is different from provider failure. The resolver asks
the same application alias for one repair; a second invalid result becomes
`INVALID_MODEL_OUTPUT` and does not trigger a provider fallback.

## StoryGuard implementation

`config/litellm.yaml` owns deployment routing. The production alias
`storyguard-entity-resolution` maps to two LiteLLM deployments sharing one
application alias: `gemini/gemini-3.5-flash-lite` and
`gemini/gemini-3.1-flash-lite`. LiteLLM's default simple-shuffle strategy picks
a deployment for each call. A timeout, rate limit, or server error gets one
bounded model-group retry, which can use another healthy deployment, before the
only fallback alias, `storyguard-entity-resolution-local`, calls
`ollama_chat/gemma4:e4b` once.

`config/models.yaml` owns the promoted application choice and model metadata.
`backend/app/ai/extraction_models.py` accepts only server-owned configuration
names. `backend/app/ai/entity_resolution.py` never accepts a raw provider model
from the caller and maps LiteLLM deployment IDs back to concrete provider/model
metadata for traces and audit records.

An invalid response is repaired through the application alias, so the repair
request can be served by either Flash Lite deployment. This is still output
repair, not provider fallback; two invalid responses become
`INVALID_MODEL_OUTPUT`.

`backend/app/queue/tasks/entity_resolution.py` persists each failed pair attempt
before retrying it. Retryable provider failures receive at most one later job
attempt after a five-second delay. `INVALID_MODEL_OUTPUT` and rejected requests
are terminal. Other candidate pairs continue, and already committed decisions
survive later failures.

The short delay deliberately uses `asyncio.sleep` instead of introducing Redis,
a scheduler service, or a RabbitMQ plugin. It occupies one worker slot for five
seconds and is not a durable timer: a worker crash in that window can leave the
job queued until Resume. Lesson 10.1 can revisit this only if failure testing
shows the limitation matters.

## Controlled experiment

The fixed test set contained 19 cases. Candidate generation produced 18 model
comparisons and missed one case for both configurations. Prompt, fixture, model
behavior code, and evaluation logic were held constant.

| Metric | Local Gemma 4 | Gemini 3.5 Flash Lite |
| --- | ---: | ---: |
| Model decision accuracy | 17/18 (94.44%) | 18/18 (100%) |
| End-to-end accuracy | 17/19 (89.47%) | 18/19 (94.74%) |
| Incorrect merges | 1 | 0 |
| First-pass valid structured output | 100% | 100% |
| Repair rate | 0% | 0% |
| Median latency | 20.56 s | 0.84 s |
| p95 latency | 29.66 s | 1.42 s |

Gemini improved model accuracy by 5.56 percentage points and end-to-end accuracy
by 5.26 points. The entire measured quality gain is one case,
`nearby-surname`: local Gemma merged Daria with Daria Chen, while Gemini returned
the labeled `needs_review`. The small dataset therefore makes the result useful
but not strong statistical evidence.

The Google AI Studio Free Tier was developer-declared, so billed cost was not
reported and the experiment records a declared cost of zero. At the documented
paid rates, the 18 calls would cost an estimated $0.005974 total, or about
$0.000332 per model case, below the approved $0.001 threshold.

The developer accepted Free Tier manuscript privacy terms for this learning
project and promoted Gemini because the measured quality and latency gains met
the chosen thresholds. Local Gemma remains the offline fallback. A later pool
experiment confirmed that this did not generalize to every Google-hosted model.

### Flash Lite pool experiment

The same fixture, prompt, candidate generation, and evaluation path compared
Gemini 3.1 Flash Lite and API Gemma 4 31B against the promoted Gemini 3.5 Flash
Lite baseline. The approved admission gate allowed at most a two-percentage-point
accuracy regression and required at least 98% valid structured output.

| Metric | Gemini 3.5 Flash Lite | Gemini 3.1 Flash Lite | API Gemma 4 31B |
| --- | ---: | ---: | ---: |
| Model decision accuracy | 18/18 (100%) | 18/18 (100%) | 9/18 (50%) |
| End-to-end accuracy | 18/19 (94.74%) | 18/19 (94.74%) | 9/19 (47.37%) |
| First-pass valid output | 100% | 100% | 50% |
| Provider errors | 0/18 | 0/18 | 9/18 |
| Median latency | 0.84 s | 0.86 s | 19.63 s |
| p95 latency | 1.42 s | 1.69 s | 34.98 s |
| Paid-tier estimate | $0.005974 | $0.004351 | unavailable |

Gemini 3.1 Flash Lite had no accuracy regression, no output repair, and no
provider error. Its paid-tier estimate was about $0.000242 per model case;
declared Free Tier cost remained zero. It passed the gate and was promoted as a
second production deployment under the existing application alias.

API Gemma 4 31B returned correct decisions on its nine successful calls, but
the other nine calls ended in provider 500 errors. Its 50% effective accuracy,
50% first-pass success, and much higher latency failed the gate. It was removed
from active routing. Gemini 2.5 Flash Lite returned 404 in its strict-output
smoke and was excluded before the full evaluation; that observation applies to
this endpoint/configuration, not every possible use of the model.

## Experiment and traces

- API candidate experiment: `gateway-v1-test-79d049d6`.
- Flash Lite pool candidate experiment: `gateway-v1-test-f8530f1e`.
- Candidate artifact: `.local/experiments/gateway-v1-test-gemini35-lite.json`.
- Pool candidate artifact:
  `.local/experiments/gateway-v1-api-pool-candidates.json`.
- Local baseline artifact: `.local/experiments/gateway-v1-test-final.json`.
- Production fallback artifact:
  `.local/experiments/gateway-v1-production-local-fallback.json`.
- Representative per-case LangSmith trace IDs:
  - `01a09a87-e76a-7a11-bd0a-567fc90364dd`
  - `01a09a88-8a28-72f1-925c-1bd51c2ec5fa`
  - `01a09a89-70a9-7240-9a60-6330d5058d84`

The candidate artifact contains all 18 per-case trace IDs. Trace metadata stores
the application alias, concrete deployment ID, resolved provider/model, retry
and fallback counts, latency, usage, and safe error classes. Provider keys,
provider response bodies, and manuscript excerpts are excluded from minimal
traces.

The pool artifact contains 18 trace IDs for each evaluated API model. Example
Gemini 3.1 Flash Lite traces are
`01a09b33-d168-75d0-b30d-171ff3f09633` and
`01a09b33-ebba-7812-adc7-f07105d6064f`. Example API Gemma 4 31B traces are
`01a09b35-7599-78c0-a566-2399d093649e` and
`01a09b35-e17e-7843-bce2-8890fe1375f5`.

## Failure evidence

Gemini 3.6 Flash first produced valid structured output but exhausted its 20 RPD
Free Tier quota during the test run. That partial result was retained as a
diagnostic and never mixed with the Gemini 3.5 Flash Lite result.

API Gemma 4 31B's first strict-output smoke returned a provider 500; the one
allowed retry returned valid JSON. The full fixed run then produced nine 500s
in 18 model calls, establishing that this was an operational reliability issue,
not a single transient incident.

The isolated fallback checks established both directions:

- local primary: two failed calls, then one successful Gemini fallback;
- promoted Gemini primary: two failed calls, then one successful local fallback.

The first local fallback smoke used an unrealistic 128-token output cap. Gemma
spent it on reasoning and returned no JSON. Repeating once with the production
1536-token cap returned valid structured output. This was a test-configuration
failure, not a routing failure.

## Load balancing decision

StoryGuard now has two independently evaluated API deployments under the stable
`storyguard-entity-resolution` alias. LiteLLM simple-shuffle load balancing was
smoked with four strict-JSON production-alias requests: three reached deployment
`sg-resolution-prod-gemini35-lite-v1` and one reached
`sg-resolution-prod-gemini31-lite-v1`; all four outputs were valid. This proves
both deployments are reachable through the alias, not that a four-call sample
establishes long-run fairness.

The pool deliberately excludes API Gemma 4 31B and Gemini 2.5 Flash Lite based
on the failures above. Multiple keys in one Google project do not multiply
project quota, and StoryGuard does not create or rotate projects to evade
provider controls. Local Gemma remains the offline final fallback.

## Tests and operational checks

- Full non-opt-in backend suite: 128 tests passed, 50 integrations skipped by
  their explicit environment flags.
- Entity-resolution DB/gateway suite: 44 passed, one 61-second regression test
  intentionally skipped.
- LiteLLM Compose configuration loaded healthy.
- Production alias returned deployment ID
  `sg-resolution-prod-gemini35-lite-v1` before the pool promotion.
- Post-promotion production smoke reached both Flash Lite deployment IDs across
  four calls with valid strict JSON.
- The live local fallback returned after two primary calls and one fallback.
- YAML validation and `git diff --check` passed.
- Post-promotion gateway contracts passed 8/8; the full backend unit suite
  passed 128 tests with 50 opt-in integrations skipped.

## Interview questions

1. Why should application code use an alias instead of a provider model ID?
2. How does structured-output repair differ from provider retry and fallback?
3. Why can several deployments under one alias make quality nondeterministic?
4. Why do multiple API keys in one Google project not multiply quota?
5. Why did one additional correct test case satisfy a five-point threshold but
   still provide weak statistical evidence?
6. What is gained and lost by the five-second in-worker retry delay?
7. Which telemetry proves that the fallback, rather than the primary, answered?
8. Why does observing both deployment IDs prove routing reachability but not an
   even long-run distribution?
