---
name: storyguard-security-review
description: Interactively review StoryGuard security for prompts, RAG, tool routing, project/version isolation, uploads, citations, model routing, queues, and LangSmith privacy.
---

# StoryGuard Security Review

1. Explain affected trust boundary.
2. Ask developer to predict one attack/failure.
3. STOP.
4. Discuss prediction.
5. Propose adversarial test plan.
6. Ask approval.
7. Add tests/fixes only after approval.
8. Give developer one attack/check to reproduce manually.
9. Discuss observation.
10. Save security/learning artifact only after understanding.

Applicable tests:
- indirect prompt injection;
- system-prompt extraction;
- unauthorized tool call;
- arbitrary model selection;
- cross-project leak;
- old-version leak;
- fake evidence ID;
- arbitrary SQL/ES DSL/path/object key;
- unsafe HTML;
- secret leakage;
- sensitive LangSmith trace leakage.
