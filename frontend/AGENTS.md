# StoryGuard Frontend Instructions

Read root `AGENTS.md` and UI spec.

Root approval gate applies.

Rules:

- StoryGuard is evidence-first, not a generic chatbot.
- Manuscript is read-only in v1.
- Normal Search and Ask StoryGuard are distinct.
- AI claims expose citations/evidence.
- Developer mode exposes execution metadata, never hidden chain-of-thought.
- Do not render unsanitized arbitrary LLM HTML.
- Do not expose provider secrets.
- Browser never calls LLM/Elasticsearch/MinIO/LangSmith directly.
- Loading/progress must reflect real backend state.
