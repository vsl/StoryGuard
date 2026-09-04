# Coreference + Gemma promotion

## Decision

The developer explicitly promoted the combined pipeline after discussing its
mechanism, timings and wrong-merge example. This accepts a speed-oriented local
default with known quality risk; it is not evidence that the candidate is more
accurate. Gemma remains the fallback model, with no Qwen replacement. Routing
rollback is `pipeline: gemma`; this does not undo already-applied decisions.
The later Lesson 5.2 checkpoint and learning summary are recorded in
`docs/learning/entity-resolution.md`.

## Hypothesis and measured diagnostic

Hypothesis: process groups with coreference and skip some slow per-pair Gemma
requests. Concern discussed before promotion: a wrong group can create multiple
wrong merges. Same-group membership is not a calibrated confidence threshold.

Run `coreference-gemma-528d5bc2335d` used the same five development cases from
`entity_resolution_v2.jsonl` for both arms. Fixture SHA-256:
`a6b2450da287efa8de326a369ede77c7a00e6340959499d32c193bfdb0b906f8`.
Raw results: `.local/experiments/coreference-dev-comparison.json`.
Gemma: `gemma4:e4b`, digest `c6eb396dbd59`, resolver prompt V1. Coreference model
revision: `a77857e473848d85acc01debdaa8353c59440d84`; encoder revision:
`64a8c8eab3e352a784c658aef62be1662607476f`. Exact source spans, 800-token windows,
no cross-window merging; unresolved generated candidates go to Gemma.

| Metric (five cases only) | Gemma | Coreference + Gemma |
| --- | ---: | ---: |
| LLM calls, including repairs | 5 | 4 |
| Decision accuracy | 80% | 60% |
| Merge precision | 66.7% | 50% |
| Merge recall | 100% | 100% |
| Incorrect merges | 1 | 2 |
| Review rate | 20% | 0% |
| Technical failure rate | 0% | 0% |
| Gemma wall time | 74.967 s | 53.350 s |

Coreference took 1.719 s after loading. The candidate therefore used about
55.068 s excluding its startup, about 27% less than the baseline in this single
small run. This is not a controlled throughput benchmark or a full-book speedup.
The original first download/load added 336.307 s: total candidate time including
that setup was 391.375 s. Local API charges were $0; compute is not cost-free.

## Failures and interpretation

Both arms incorrectly merged an ambiguous Nora reference. Coreference also
linked two Alex mentions from unrelated letters where identity was unsupported;
Gemma alone returned `needs_review` for that case. The only skipped Gemma call
in this diagnostic was therefore an incorrect shortcut. Lower review rate did
not represent better accuracy. No full-book benchmark or labelled book accuracy
result exists; the saved additional book remains unlabelled.

Gemma trace examples: ambiguous Nora
`01a05732-31dc-73d0-a8a5-7628b2644d6b`; Alex abstention
`01a05733-14a0-75a2-bda6-375e0e5224f1`. Original native coreference tracing was
not enabled. The Docker loader verification recorded
`01a0575e-db87-7f63-841a-40fa3066c4c7`.

## Runtime integration

`config/models.yaml` selects `coreference_gemma`. The resolution worker prepares
the existing bounded candidate set, runs/caches coreference in an isolated
Python 3.11 subprocess, processes aligned shortcuts first, then calls Gemma.
Both branches use existing audited prediction/application transactions. Original
mentions, server-issued evidence, project/version scope and separation constraints
are retained. Technical coreference failure falls back visibly, never pretending
that xCoRe produced accepted groups. Cached output contains offsets and source
hashes, not manuscript text; temporary inference input is removed after the run.

The upstream loader was killed with exit 137 in the 7.75-GiB Docker environment.
The replacement avoids loading redundant base weights: restricted
`weights_only=True` deserialization, memory-mapped weights, shape-only model
construction and strict parameter assignment. No unrestricted pickle loading is
enabled. Native and Docker outputs matched the original five groups exactly.
With downloaded files cached, the revised Docker run took 5.171 s, including
1.710 s inside model loading; Python imports/process startup are outside those
runner timings. This remains a short-passage check, not full-book performance.

Completed caches are version/content/runner/dependency keyed. A shared file lock
limits heavy scans to one process, and Stop kills active inference. A 30-minute
wait/scan deadline is independent of the existing Gemma batch budget. Original
candidate coverage and batch limits remain unchanged. New runs/resumes use the
new routing; saved earlier decisions are not silently reconsidered.

## Verification

- Final deployed backend: 88 tests, 86 passed / 2 optional skips. Coverage includes
  skipped Gemma calls, audit provenance, existing separation constraints, visible
  fallback, Stop/late-result fencing, cache source/version isolation and child
  termination. Native unit discovery also passed; native DB discovery without
  the full Compose environment failed on missing `RABBITMQ_URL`, so the complete
  integration suite was verified inside the configured backend container.
- Frontend: 14 tests, lint, TypeScript and production build passed.
- Real browser smoke: passed in 52.6 s against live APIs/storage/worker/models.
  Two chapters produced one xCoRe merge and one Gemma comparison; both merges
  applied automatically, Stop/Resume worked, aliases/evidence appeared, and no
  technical errors remained. This is functional verification, not a speed/accuracy
  comparison. The earlier Alex-platform fixture produced no xCoRe link (correct
  fallback), so the final smoke passage explicitly describes the same person.
- Initial Chromium launch was blocked by the shell sandbox; the successful run
  used the approved browser launch outside it. No API routes were mocked.
- Screenshot: `frontend/test-results/real-entity-resolution-rea-143ab-es-an-evidence-backed-merge/combined-resolution.png`.
- Live combined-run coreference trace: `01a05768-7c58-7d02-b111-c8b0594e20c4`.
- No schema change or database reset. Only disposable smoke projects were
  removed; the existing user project and its two completed jobs remained.

The later developer checkpoint inspected the correlated LangSmith batches,
distinguished xCoRe and Gemma decisions from manuscript evidence, and verified
the final Story Bible navigation. No automatic reprocessing was started solely
to complete the course record.
