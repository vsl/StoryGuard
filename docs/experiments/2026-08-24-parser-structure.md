# Parser Structure Experiment

## Hypothesis

Extending deterministic text rules for sequential numeric headings,
Roman-numbered titled headings, and TXT `#` scene separators should recover real
narrative structure. The expected risk was false headings from numbered lists or
Roman numerals in prose.

## Developer prediction

Recall should improve because the baseline misses known chapter and scene styles.
False positives may increase, so the candidate must be tested against negative
controls rather than judged only by how many sections it produces.

## Baseline and candidate

- baseline: parser `v1`, `Chapter N`/prologue/epilogue and existing explicit scene
  separators;
- candidate: parser `v2`, plus monotonic numeric and Roman-title sequences and
  standalone `#` scenes in TXT;
- numeric/Roman sequences require at least three headings and at least 200
  narrative characters between adjacent candidates;
- scene-looking markers in front matter do not create scenes.

## Dataset and labels

The exact-boundary set contains four documents:

- pinned Gutenberg IDs `11`, `120`, and `1661` from the local dataset fixture;
- Cory Doctorow's official `Little Brother` TXT, CC BY-NC-SA 3.0, SHA-256
  `24ac213b5bd7840df63f3bf970fee9bcdaec19a0dc994a4eb66e72ae56d3aa66`.

`backend/tests/fixtures/parser_boundaries.json` stores 80 chapter and 77 scene
line positions. Every label set is bound to the SHA-256 of its normalized source.
The evaluator rejects source drift before scoring. Candidate positions come
directly from parser metadata and are compared by exact 1-based normalized line
number. Compact numbered/Roman lists, Markdown `#`, DOCX headings, offsets, and
front matter are covered by golden unit tests.

## Metrics

| Exact boundary metric | Baseline v1 | Candidate v2 |
|---|---:|---:|
| Chapter TP / FP / FN | 34 / 0 / 46 | 80 / 0 / 0 |
| Chapter precision | 100% | 100% |
| Chapter recall | 42.5% | 100% |
| Chapter F1 | 59.65% | 100% |
| Scene TP / FP / FN | 0 / 0 / 77 | 77 / 0 / 0 |
| Scene precision | undefined | 100% |
| Scene recall | 0% | 100% |
| Scene F1 | 0% | 100% |
| Fallback documents | 2 / 4 | 0 / 4 |
| Total chunks | 670 | 707 |

All candidate `false_lines` and `missing_lines` lists were empty. The additional
structure increased chunks by 37 (5.52%) because chunks never cross detected
chapter or scene boundaries.

## Latency and cost

One local run measured about 155 ms for baseline and 127 ms for candidate across
all four books. This single timing is too noisy to interpret. There were no LLM,
embedding, Elasticsearch, LangSmith, or paid API calls.

## Failure analysis

The first evaluator compared chapter identities and scene counts. That was too
weak: the correct number of boundaries at wrong positions could pass. It was
replaced before promotion with exact line-position labels and source hash checks.

The 100% result applies only to these four documents and golden negative cases.
A book with only two bare-number headings intentionally falls back because the
three-heading guard favors precision. Unknown publisher layouts remain an open
evaluation risk. Exact raw-file byte offsets are not stored; scene and chunk
offsets are relative to normalized chapter text.

## Developer conclusion and discussion

The developer concluded that 100% shows the parser works on the current data but
does not prove the same result on new data. This is correct. Precision, recall,
and F1 here measure parser boundaries, not retrieval; Recall@K will be introduced
with BM25.

## Decision

The developer explicitly promoted parser `v2` as the deterministic baseline.
No LLM parser was added. Expand the labeled corpus when a new real formatting
failure is observed.
