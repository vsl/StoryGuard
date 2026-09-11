# StoryGuard Codex Workflow

## Normal use

You normally type only:

```text
$storyguard-course-lesson
```

That is enough.

The skill reads:

```text
COURSE_PROGRESS.md
→ COURSE.md
→ relevant specs
```

and continues automatically.

Always resume the position in `COURSE_PROGRESS.md`; do not infer it from the
original course pack. The focused curriculum in `COURSE.md` preserves completed
lessons and defines nine remaining core lessons after 5.3. Optional labs are
chosen explicitly, never required to graduate or selected automatically.

Build grounded QA, bounded planning/tools, and character-attribute continuity
review using the existing stack. Integrate and secure each feature as it is
built; final lessons harden the demo and rehearse interview explanations.

---

# Expected Dialogue

Example:

Codex:

```text
Why should PostgreSQL be the source of truth while Elasticsearch is only a retrieval index?
```

You answer.

Codex MUST respond in chat:

```text
✅ What you got right
...

⚠️ What is missing
...

🧠 Mental model
PostgreSQL = authoritative structured state
Elasticsearch = derived searchable representation

🔗 StoryGuard mapping
...

🛠 Proposed implementation
1...
2...
3...

Approve this implementation plan?
```

Then it stops.

Only after:

```text
yes
```

may it edit files.

---

# If Codex Writes Files Too Early

Say only:

```text
Stop. Follow the dialogue-first protocol in AGENTS.md.
```

You do NOT need to paste the full rules again.

---

# Other Skills

## Experiment

```text
$storyguard-ai-experiment
```

Use when intentionally changing:
- retrieval;
- prompt;
- model;
- routing;
- embeddings;
- reranker;
- planner;
- HyDE;
- verifier;
- hallucination behavior.

You predict first.
Codex runs after approval.
You interpret the metrics before promotion.

## Learning / interview review

```text
$storyguard-learning-review
```

Example:

```text
$storyguard-learning-review
Interview me on the retrieval architecture.
```

It should discuss your answers, not save them automatically.

## Security

```text
$storyguard-security-review
```

Use around prompts/RAG/tools/model routing/project isolation/uploads/citations.

## Off-course feature

```text
$storyguard-feature
```

Use only if intentionally implementing something outside the normal lesson sequence.

---

# Recommended Daily Flow

```text
$storyguard-course-lesson
```

Then just converse naturally.

You do not need special commands for:
- your lesson answers;
- approval;
- checkpoint observations.

Example:

```text
Codex asks...
You answer normally.

Codex proposes plan...
You: yes

Codex implements and gives checkpoint...
You report what you saw.
```

The skill owns the workflow.
