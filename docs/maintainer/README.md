# Maintainer workspace

Personal course, interview preparation, and development workflow documents live
here. This directory is tracked in the public repository; it is not private.
Public entry points focus on application capabilities, architecture, setup, and
engineering evidence, without linking to this workspace.

## Continue working

Use the same command as before:

```text
$storyguard-course-lesson
```

Codex reads [course progress](COURSE_PROGRESS.md) first, then the
[curriculum](COURSE.md). Progress is the only source of the current lesson and
checkpoint state; moving these files does not complete or restart a lesson.

| Document | Purpose |
| --- | --- |
| [Course progress](COURSE_PROGRESS.md) | Current lesson, completed lessons, and checkpoint state |
| [Curriculum](COURSE.md) | Required scope, lesson sequence, and optional labs |
| [Commands](USER_COMMANDS.md) | Course, experiments, review, security, and off-course features |
| [Codex workflow](CODEX_WORKFLOW.md) | Dialogue, approval, implementation, and learning gates |
| [Interview guide](interview-guide.md) | Project introduction, architecture walkthrough, questions, and practice checkpoint |
| [Learning notes](../learning/README.md) | Completed understanding and implementation evidence |
| [Experiment reports](../experiments/README.md) | Historical comparisons and promotion decisions |

## Agent entry points and source documents

[Root instructions](../../AGENTS.md) remain at the repository root. Skills stay
discoverable under [.agents/skills](../../.agents/skills); their command names
are unchanged. Instruction paths are repository-relative; Markdown links are
relative to the document containing them.

- [Architecture guide](../architecture/README.md): current implementation and limitations.
- [Backend and AI specification](../specs/storyguard_backend_ai_spec.md): locked design and evidence invariants.
- [UI specification](../specs/storyguard_ui_spec.md): frontend contracts and delivery boundaries.
- [Frontend/API gaps](../frontend-api-gaps.md): actual integration coverage and deferred capabilities.

Follow the documentation maintenance rule in root `AGENTS.md`: update affected
documents during approved work, preserve historical measurements, and keep
course progress and learning artifacts behind their existing completion gates.
