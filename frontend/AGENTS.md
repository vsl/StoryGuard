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

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
