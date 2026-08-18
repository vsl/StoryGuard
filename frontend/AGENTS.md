# Frontend Rules

Read root `AGENTS.md` and `docs/specs/storyguard_ui_spec.md`.

- StoryGuard is an evidence-first narrative consistency copilot, not a generic ChatGPT clone.
- Manuscript viewer is read-only in v1.
- Normal Search and Ask StoryGuard remain distinct.
- Important AI claims expose citations/evidence.
- Loading/progress states reflect real backend state.
- Never render arbitrary unsanitized LLM HTML.
- Developer mode shows observable execution metadata, never hidden chain-of-thought.
- Use Likely / Possible / Needs review, not ERROR.
- Browser code never calls OpenAI/LiteLLM/LangSmith/MinIO/Elasticsearch directly.
