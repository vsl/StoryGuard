# StoryGuard AI Layer Instructions

Read root `AGENTS.md` and backend AI spec.

No AI behavior changes before the dialogue + experiment approval flow.

Invariants:

1. Program-driving LLM outputs use structured schemas.
2. Evidence IDs are server-owned.
3. HyDE is never evidence.
4. Project/version scope is server-enforced.
5. Planner/tool/retrieval/LLM loops are bounded.
6. Tool access is allowlisted by route.
7. Manuscript content is untrusted data.
8. Business logic uses semantic LiteLLM aliases.
9. Unsupported claims => one repair, then remove/abstain.
10. Significant AI nodes are traced in LangSmith.
11. Never expose hidden chain-of-thought.
