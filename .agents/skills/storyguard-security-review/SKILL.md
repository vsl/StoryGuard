---
name: storyguard-security-review
description: Review StoryGuard security boundaries for changes involving prompts, RAG/retrieval, tool routing, uploads, project or manuscript-version scoping, LiteLLM/model routing, external services, queues, citations, or sensitive tracing.
---

# StoryGuard Security Review
Treat user input, manuscript text, retrieved chunks, filenames/uploads, and model output as untrusted.

Check applicable attacks: prompt injection, system prompt extraction, unauthorized tools, arbitrary model/provider selection, cross-project retrieval, old-version retrieval, hallucinated evidence IDs, SQL/ES DSL/path/object-key injection, unsafe HTML, secret exposure, sensitive LangSmith traces.

Verify server-side scope/tool/evidence/model allowlists.

Report boundaries, tests, findings, fixes, and residual risks. A failed security regression test means the change is not complete.
