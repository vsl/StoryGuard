---
name: storyguard-feature
description: Implement a specific StoryGuard feature outside the normal course sequence. Discuss consequential design choices and get explicit approval before implementation.
---

# StoryGuard Feature

Use only when intentionally working outside the normal `docs/maintainer/COURSE.md` sequence.

1. Read root `AGENTS.md` and relevant specs.
2. Inspect code first.
3. Explain intended behavior and request/data flow.
4. Surface consequential choices.
5. Give recommendation/trade-offs.
6. Ask for explicit approval.
7. STOP.
8. Implement only after approval.
9. Add/run tests.
10. Explain actual code path.
11. If AI behavior changed, use `storyguard-ai-experiment`.
12. If security boundary changed, use `storyguard-security-review`.
13. Update affected public and maintainer documentation per root `AGENTS.md`; preserve course progress and learning gates.

Do not silently alter `docs/maintainer/COURSE_PROGRESS.md` for off-course work unless it actually completes a course requirement and the developer approves that mapping.
