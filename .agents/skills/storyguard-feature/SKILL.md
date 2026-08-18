---
name: storyguard-feature
description: Implement or change a StoryGuard product feature as a reviewable vertical slice. Use for backend, frontend, ingestion, data model, queue, API, or end-to-end feature work. Do not use for a pure AI behavior experiment; use storyguard-ai-experiment instead.
---

# StoryGuard Feature Workflow
1. Read root `AGENTS.md` and relevant spec sections.
2. Inspect existing code.
3. State acceptance criteria, affected layers, migrations/API/background/AI implications, and unresolved decisions.
4. If a consequential decision is unspecified, stop and ask.
5. Implement one coherent vertical slice, not future lessons.
6. Add/update tests and run them.
7. Run relevant Docker smoke checks.
8. If AI behavior changed, follow `storyguard-ai-experiment`.
9. If security boundaries changed, follow `storyguard-security-review`.
10. Update learning/ADR docs when required.
11. Return the completion report from root `AGENTS.md`.
