# StoryGuard Course Progress

This file is the persistent course cursor.

`$storyguard-course-lesson` MUST read this file first and continue from here.

## Current position

```yaml
course_status: in_progress

completed_lessons:
  - "0.1 System boundaries"
  - "0.2 Docker/local architecture"
  - "1.1 FastAPI + PostgreSQL"

current_lesson:
  id: "1.2"
  title: "MinIO + manuscript versions"
  status: "developer_checkpoint"

current_lesson_state:
  concept_discussed: true
  implementation_plan_approved: true
  implementation_done: true
  tests_done: true
  developer_checkpoint_done: false
  learning_done: false
```

## Important

Lessons `0.1` and `0.2` were already completed before this progress file was introduced.

Do NOT make the developer repeat them unless they explicitly request a review.

Do NOT invent retrospective learning notes for those lessons unless the developer asks for them.

## Progress update rules

The normal sequence for a lesson is:

```text
not_started
→ concept discussion in chat
→ implementation plan proposed
→ developer explicitly approves
→ implementation
→ tests / evals / traces
→ developer checkpoint
→ checkpoint discussion
→ learning note
→ lesson complete
→ advance to next lesson
```

### Before approval

Do NOT update repository files merely to store the developer's learning answers.

The course discussion remains in chat.

### After implementation approval

Codex may update this file to record implementation progress.

### Lesson completion

Only mark a lesson complete when BOTH are true:

```text
implementation_done = true
learning_done = true
```

Then:
1. append the lesson to `completed_lessons`;
2. set the next lesson from `COURSE.md` as `current_lesson`;
3. reset all `current_lesson_state` booleans to false.

## Recovery rule

If this file and the actual repository state disagree:

1. inspect the repository/tests/learning notes;
2. explain the mismatch in chat;
3. propose the corrected course state;
4. ask the developer for approval;
5. only then update this file.
