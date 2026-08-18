# AI Layer Rules

Read root `AGENTS.md` and `docs/specs/storyguard_backend_ai_spec.md`.

## Invariants
1. LLM outputs that control program behavior use structured schemas.
2. Evidence citations are server-owned IDs, not model-invented source strings.
3. HyDE content is never evidence.
4. Retrieval is always scoped server-side to project + manuscript version.
5. Agent loops/tool calls/retrieval rounds/planner subquestions/LLM calls are bounded.
6. Tool access is allowlisted per route.
7. Manuscript content is untrusted data.
8. Model selection uses semantic LiteLLM aliases.
9. Unsupported factual claims are repaired once, removed, or trigger abstention.
10. Significant AI nodes are traceable in LangSmith.
11. Never store/expose hidden chain-of-thought.

Before modifying AI behavior, use `storyguard-ai-experiment`.

Debug quality in this order: routing -> retrieval -> reranking -> evidence coverage -> structured output -> synthesis -> verifier/citations -> model/fallback.
