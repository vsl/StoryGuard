# Hugging Face Dataset Lifecycle

## Mental model

```text
registry = where and how to load
manifest = exact expected output identity
cache    = disposable download optimization
fixture  = generated local data

commit SHA = immutable address
main       = moving pointer
```

A dataset repository revision alone does not fully identify an experiment input.
StoryGuard also pins the configuration, split, selected record IDs or row indices,
transformation version, and content checksums.

## StoryGuard implementation

- `config/datasets.yaml` is the registry for the Gutenberg manuscript corpus,
  Story QA cases, and retrieval benchmark. It records full commit SHAs, configs,
  splits, selectors, fixture paths, provenance, and license notes.
- `backend/scripts/bootstrap_datasets.py` loads only pinned revisions, selects the
  configured records, validates required fields and license metadata, writes
  deterministic JSONL atomically, and calculates record/file SHA-256 hashes.
- `data/datasets/manifest.json` is the committed identity of the generated subset.
  It contains the actual record hashes, output hashes, counts, source coordinates,
  and transformation version.
- `data/datasets/fixtures/*.jsonl` contains the generated text data and remains
  local through `.gitignore` because the source datasets are large and some
  upstream texts have redistribution restrictions.
- `backend/tests/test_dataset_bootstrap.py` proves deterministic regeneration,
  forwards revisions and streaming options, and verifies that source drift fails
  before an existing fixture is overwritten.

Bootstrap flow:

```text
config/datasets.yaml
-> load_dataset(hf_id, config, revision, split, streaming=True)
-> select stable IDs or pinned row indices
-> validate schema and provenance constraints
-> normalize to deterministic JSONL
-> calculate per-record and file SHA-256
-> compare with the committed manifest
-> atomically replace local fixtures
```

The current bootstrap produces:

```text
3  public-domain manuscripts
10 Story QA cases
20 retrieval queries
3  referenced retrieval chunks
```

Gutenberg uses a pinned Hugging Face Parquet-conversion revision plus the pinned
source revision. Predicate pushdown reads only IDs `11`, `120`, and `1661`
instead of scanning the multi-gigabyte JSON corpus. NarrativeQA has no upstream
record ID, so StoryGuard records the pinned row index and derives an ID from the
source content hash. Retrieval queries similarly use content-derived IDs, while
their evidence chunks retain upstream `chunk_id` values.

## Why this design

- A full commit SHA cannot move; `main` may point to different bytes tomorrow.
- Stable selection metadata prevents a pinned source from producing a different
  subset because of changed filtering, randomness, or row choice.
- Deterministic serialization makes file hashes comparable across runs and
  machines.
- The committed manifest detects silent source or transformation drift without
  committing large text fixtures.
- The Hugging Face cache is not trusted as the dataset contract. It may be
  removed; registry plus manifest must still reconstruct and verify the subset.
- A database registry, generic dataset framework, upload service, and full-corpus
  download were not added because this offline bootstrap does not need them.

## Failure behavior

The bootstrap stops if a selected ID/index is missing, an expected string field
is empty, a source ID is duplicated, a Gutenberg record is not marked Public
Domain, or newly generated hashes differ from the committed manifest. All remote
reads and validation finish before local output replacement, and each file uses
an atomic same-directory replace.

If `revision` were changed from a full SHA to `main`, the command might still pass
today, but reproducibility would no longer be guaranteed. A future upstream
commit could change or reorder selected rows; the generated hashes would then
differ and StoryGuard would reject the result.

## Verification and observations

- Backend suite: 11 tests discovered, 6 passed, 5 integration tests skipped
  behind their normal environment flags, 0 failed.
- Two real Hugging Face bootstrap runs produced the identical manifest SHA-256:
  `3b866dd0693ad5e0682f60d0546bed44138f3711f39710c31e7a936fd991e2b3`.
- The developer moved the local Story QA fixture away, reran the bootstrap, and
  observed that the restored file and backup both had SHA-256
  `295e1543312839f2d778986fab2dd3286894c8c9b1622b0384711e308fc7484c`.
- The initial Gutenberg JSON scan was aborted after several minutes. Loading the
  pinned Parquet conversion with an ID filter reduced observed bootstrap time to
  roughly 14–20 seconds in the verification runs.

There were no LLM calls, LangSmith traces, AI evaluations, or API charges. The
only cost is local disk/CPU and Hugging Face network traffic. Unauthenticated Hub
access may be rate-limited, but authentication is not required for these public
datasets.

## Security and reliability

- Full revisions prevent silent branch movement.
- Remote text is treated only as data; the bootstrap does not execute dataset
  code or manuscript content.
- Generated copyrighted or uncertain-license text remains untracked locally.
- Gutenberg records must carry the expected Public Domain source metadata, but
  that metadata is not a legal guarantee; territorial rights still require review
  before redistribution.
- Existing committed manifest data causes unexpected drift to fail closed.

## Interview questions

1. Why is pinning a dataset commit SHA necessary but not sufficient for
   reproducible evaluation?
2. What is the difference between a dataset cache, fixture, registry, and
   manifest?
3. How should records be identified when an upstream dataset has no stable ID?
4. Why can `main` silently invalidate comparisons between experiment runs?
5. How do deterministic serialization and checksums detect dataset drift?
