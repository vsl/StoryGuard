# StoryGuard Dataset Strategy

StoryGuard uses real narrative data instead of requiring the developer to write entire books.

This is a personal non-commercial portfolio project, with no production use or
planned sale. Non-commercial datasets and models are acceptable; preserve source
notices, attribution, license terms, and revisions. This is an established project
decision, not a recurring blocker. Reconsider only if intended use changes.

## Current entity fixtures

Supported types: `character`, `facility`, `gpe`, `location`, `organization`,
`vehicle`: characters/people, constructed sites, countries/settlements, natural
locations, organizations, and vehicles. Scope is independent of model choice.

Current fixtures under `data/datasets/fixtures` are `entity_extraction_v3.jsonl`,
`entity_extraction_model_eval_v3.jsonl`, and `entity_resolution_v2.jsonl`.
Earlier fixtures/results are historical, not current quality claims. The new
labels distinguish facilities, settlements and vehicles and omit excluded
artifacts and abstract concepts. Resolution V2 adds facility, vehicle and natural
location cases. Both experiment arms must use the same new fixture version;
filtered results must not be compared to old aggregate scores.

## Isolated coreference comparison

The developer promoted xCoRe + Gemma after reviewing the small diagnostic;
the CLI below remains a comparison tool and never changes database identities.
The same policy is now used by the worker: exact original-text spans in one predicted
coreference cluster as a merge shortcut, with Gemma for unresolved pairs.
That shortcut is a hypothesis, not a calibrated confidence guarantee: a wrong
cluster can cause wrong merges. Missing links never mean “keep separate”.
Windows are bounded to 800 tokens by default; cross-window links are not joined.

Run from the repository root, with the local Compose stack available:

```sh
uv venv --python 3.11 .local/xcore-venv
uv pip install --python .local/xcore-venv/bin/python -r backend/scripts/coreference_requirements.txt
docker compose run --rm --no-deps worker python -m scripts.coreference_experiment --split dev --export-input /local/experiments/coreference-dev-input.json
HF_HOME="$PWD/.local/xcore-models" .local/xcore-venv/bin/python backend/scripts/coreference_predict.py --input .local/experiments/coreference-dev-input.json --output .local/experiments/coreference-dev-cache.json --cache-dir .local/xcore-models
docker compose run --rm --no-deps worker python -m scripts.coreference_experiment --split dev --coreference /local/experiments/coreference-dev-cache.json --output /local/experiments/coreference-dev-comparison.json
```

Skip environment creation/installation when already prepared. The isolated
Python runtime avoids changing the application's dependencies. Checkpoint
revision is pinned in the runner; resolved encoder revision and runtime
versions are recorded. The live loader pins the encoder revision too, constructs
parameter shapes without redundant base weights, and strictly assigns the same
memory-mapped checkpoint. Loading stays restricted to weights and explicitly
allowlisted metadata; never disable weights-only loading. First execution
downloads several GB. Keep cold download/load time separate from cached-model
inference and Gemma fallback time when interpreting latency.

The comparison validates cache source hashes and uses the same versioned cases
for both arms. It records decisions, errors, request counts (including repairs),
token usage and Gemma trace IDs. Coreference trace IDs require LangSmith to be
configured in the isolated process; traces omit manuscript text. Raw results
stay under ignored `.local/experiments`. The five development cases are a
diagnostic, not full-book accuracy evidence. Use `--split test` with separate
input/cache/result filenames for the frozen test cases; do not tune on them.
No database identities are changed and no model is promoted by these commands.

## Additional full-manuscript test input

E. Nesbit's *The Railway Children* is saved at
`.local/test-book.KMZ5lS/the-railway-children.txt`, with provenance in `source.json`.
Source: https://www.gutenberg.org/ebooks/1874 (14 chapters).
SHA-256: `8050f391661c1c45bd65c9584b4f93dec46cfc07cc7352e2169899f1e664b290`.
The original download and license notice are preserved. This is an unlabelled
ingestion/performance input, not an accuracy benchmark or proof of absence from
model pretraining. Use separately annotated examples for identity scoring.

## Public-domain manuscripts

Hugging Face:

```text
common-pile/project_gutenberg
```

Use for:
- manuscript ingestion;
- chunking;
- Story Bible extraction;
- long-document RAG;
- controlled continuity mutations.

Use only an intentionally small pinned development subset.

## Story QA

Hugging Face:

```text
meithnav/narrativeqa
```

Use for:
- factual QA;
- multi-hop QA;
- answer correctness;
- evidence/citation eval fixtures.

## Retrieval benchmark

Hugging Face:

```text
feyninc/gacha
```

Use for:
- BM25/vector/hybrid/reranker comparison;
- Recall@K;
- MRR;
- query rewriting;
- HyDE experiments.

Pin revision `076b8b186236941df371a8d9b14be4cb4c7498fb` and use the
`corpus/train` and `questions/train` configurations. The local fixture contains
ten selected public-domain narrative books: two development books and eight
held-out test books.

Ground truth is never a supplied chunk ID. For each question, locate the exact
`chunk-must-contain` evidence in its corresponding full book, run StoryGuard's
normal parser, and label every resulting overlapping chunk containing that
evidence as relevant. Retrieval remains scoped to that book's deterministic
project and manuscript version.

Gacha is licensed CC BY-NC-SA 4.0. StoryGuard uses it only for this
non-commercial project, preserves provenance, and does not assume that a work's
US public-domain status applies in every territory.

## Continuity

Create controlled mutations from selected public-domain narratives.

Include both:
- actual contradictions;
- negative controls / non-conflicts.

## Reproducibility

Pin:
- dataset ID;
- revision;
- split;
- selected row/document IDs;
- transformation version;
- license/provenance metadata.
