# Entity Extraction

## Mental model

```text
LLM proposal
  -> server reads the claimed source span
  -> exact source-text equality
  -> trusted entity mention
```

The LLM proposes `surface_text`, `entity_type`, `start_offset`, and
`end_offset`. StoryGuard does not treat that proposal as evidence. It accepts a
mention only when the half-open span points to the same text in the stored
manuscript. In the developer checkpoint, the SQL `evidence` column was a
computed `substring(chapters.text, ...)`, not a separately stored or
model-generated field.

## StoryGuard data flow

```text
Taskiq ingestion job
  -> stored chunks
  -> LiteLLM -> Ollama -> gemma4:e4b with entity_extractor:v2
  -> Pydantic structured-output validation (one bounded repair)
  -> chunk span validation
  -> chapter-relative offsets
  -> overlap deduplication
  -> chapter evidence validation
  -> atomic replacement of entity_mentions
  -> manuscript version becomes ready
```

`backend/app/queue/tasks/ingestion.py` keeps extraction inside the existing
background ingestion job. `backend/app/entity_mentions.py` scopes every read
and write to the project and manuscript version, verifies that the chunk set
did not change during inference, and replaces mentions only after the complete
version succeeds. There is no second queue or extraction API.

The reusable AI boundary is in `backend/app/ai/entity_extraction.py`. The
stored schema is `backend/app/db/models/entity_mention.py`, created by
`backend/migrations/versions/20260828_06_create_entity_mentions.py`. Every row
keeps its chapter, optional scene, source chunk, exact half-open offsets,
surface text, entity type, prompt version, and model alias.

Lesson 5.1 stores separate textual mentions. It deliberately does not decide
whether two mentions refer to one canonical entity; that is Lesson 5.2 entity
resolution.

## Evidence and trust invariants

- Manuscript text and model output are both untrusted inputs.
- The model may only point to text that actually exists in the supplied chunk.
- `text[start_offset:end_offset] == surface_text` must hold at both chunk and
  chapter boundaries.
- Offsets are half-open and are converted from chunk-relative to
  chapter-relative before persistence.
- Project and manuscript-version scope is enforced by the server, never by the
  prompt.
- A hallucinated, malformed, or out-of-range span cannot become a stored
  mention.
- Existing rows are not partially replaced when any chunk fails.
- Prompt and model provenance make a stored extraction reproducible and
  auditable.

## Model and prompt decision

All candidates used the same frozen 24-example fixture, exact span/type
scoring, and no test-specific names or rules in the prompt.

| Candidate | Precision | Recall | F1 | Decision |
|---|---:|---:|---:|---|
| Gemma V2 (`gemma4:e4b`) | 0.9444 | 0.9444 | 0.9444 | default |
| Qwen3.5 9B | - | - | 0.8246 | not promoted |
| Qwen3.5 4B | - | - | 0.7965 | not promoted |
| GLiNER2.5 Base | 0.7368 | 0.7778 | 0.7568 | future fast-tier candidate only |

Gemma found every gold character, location, object, and organization; its weak
category was `other` recall at 0.5. GLiNER was about 278 times faster at p50
(38.3 ms versus 10,666.5 ms) and had no generative schema repairs, but produced
much more false-positive noise and missed more entities. Both local options had
zero paid API cost. Quality therefore outweighed latency for the default,
while GLiNER remains reproducible offline evidence for a future fast tier.

Experiment details are in
`docs/experiments/2026-08-30-entity-extraction-gliner25-base.md`; the retained
experiment ID is `entity-extraction-gliner25-base-v1-20260830`.

## Failure behavior

- Invalid structured output gets at most one repair attempt; repeated invalid
  output fails extraction.
- Hallucinated spans are rejected by source-text validation.
- An unavailable or timed-out model safely fails the job and manuscript
  version with `ENTITY_EXTRACTION_FAILED`; it does not replace the project's
  previous ready version.
- A scope change or changed chunk set aborts persistence.
- Common nouns and generic roles can still become false positives when their
  spans are real. Evidence validation proves provenance, not semantic
  correctness; eval precision measures that remaining risk.
- The worker owns `LITELLM_API_KEY` and performs inference. A direct call from
  the backend container failed without that secret, which confirms the intended
  process boundary rather than an ingestion defect.

LangSmith instrumentation is present, but tracing was disabled or unavailable
during this lesson, so there are no trace IDs. When enabled, traces must follow
the configured minimal/redacted/full privacy policy and must not expose raw
manuscript text by default.

## Verification

- Focused entity extraction tests: 10 passed.
- Full native backend suite: 49 passed, 12 skipped.
- Full Docker/DB suite: 49 passed, 1 skipped.
- Backend and worker images built; backend was healthy and worker was running.
- A real worker -> LiteLLM -> Ollama -> PostgreSQL smoke stored three mentions.
- The developer reconstructed each source substring in SQL and confirmed it
  exactly matched the stored `surface_text`.

## Alternatives and deferred work

- Qwen candidates were rejected on measured quality, not preference.
- GLiNER is retained only as an offline fast-tier candidate; production
  routing, threshold tuning, label-description tuning, and a GLiNER-to-Gemma
  cascade require a separate experiment with a concrete latency requirement.
- A separate endpoint, second queue, fine-tuning, and canonical entity merging
  were unnecessary for Lesson 5.1.

## Interview questions

1. Why is an exact source span necessary but insufficient evidence that an
   extracted entity is semantically correct?
2. How does StoryGuard prevent partial entity data when one chunk fails?
3. Why are entity mentions stored before canonical entities are created?
4. What evidence justified keeping Gemma as the default despite GLiNER's much
   lower latency?
5. Which provenance fields are needed to reproduce or audit an extraction?
