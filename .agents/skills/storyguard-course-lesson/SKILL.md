---
name: storyguard-course-lesson
description: Continue the StoryGuard AI Engineer course from COURSE_PROGRESS.md. Invoke with just $storyguard-course-lesson. Must discuss/correct the developer's answers in chat, propose an implementation plan, and wait for explicit approval before touching repository files.
---

# StoryGuard Course Lesson

This is the PRIMARY StoryGuard skill.

The developer should normally invoke only:

```text
$storyguard-course-lesson
```

No additional prompt is required.

---

## Step 0 — Resolve Current Course Position

FIRST read:

1. `COURSE_PROGRESS.md`
2. `COURSE.md`

Determine:

```text
completed lessons
current lesson
current lesson status
```

Rules:

- Do not repeat completed lessons.
- Current provided progress starts after Lesson 0.2.
- If `current_lesson.status = not_started`, begin that lesson.
- If a lesson is partially implemented, inspect actual repo state before deciding what to resume.
- If state is ambiguous, discuss it with the developer instead of guessing.

---

## Step 1 — Brief

Read relevant specs/code.

Explain briefly:

- lesson goal;
- why it matters in StoryGuard;
- where it sits in architecture;
- compact request/data flow;
- 3–6 English domain terms with Russian translations.

Do NOT code.

Do NOT write learning files.

---

## Step 2 — Ask

Ask 1–3 conceptual questions.

Questions should make the developer build a mental model.

Then STOP and wait.

---

## Step 3 — Review Developer Answer IN CHAT

Never silently save the answer.

Respond:

### ✅ What you got right

### ⚠️ What is missing / inaccurate

### 🧠 Mental model to remember

### 🔗 How this maps to StoryGuard

If needed, ask ONE follow-up question.

STOP.

Do not propose implementation until the conceptual misunderstanding is resolved enough to proceed.

---

## Step 4 — Propose Implementation

Show:

### 🛠 Proposed implementation

Include:

- goal;
- components/files;
- request/data flow;
- API/schema/storage changes;
- tests;
- failure scenarios;
- trace/eval/security implications;
- what is deliberately not included yet.

End with:

```text
Approve this implementation plan? (yes / change something)
```

STOP.

---

## Step 5 — Approval Gate

No repository modifications before explicit approval.

If developer changes the plan:
1. discuss;
2. revise;
3. ask for approval again.

---

## Step 6 — Implement Approved Lesson

Only after approval:

- implement only the current lesson;
- add/update tests;
- run relevant tests;
- run Docker smoke if relevant;
- run eval/security checks when relevant.

Do not implement future lessons “while here”.

After approval, update `COURSE_PROGRESS.md` as implementation progresses if useful.

---

## Step 7 — Explain Actual Implementation

In chat, walk through actual code:

```text
request/input
→ file/function
→ component
→ external dependency/storage
→ output
```

Explicitly state where the developer's earlier model/prediction differed from what was built.

---

## Step 8 — Developer Hands-On Checkpoint

Give ONE concrete manual task.

Examples:

- inspect a DB row;
- stop a dependency and observe behavior;
- inspect a LangSmith trace;
- compare retrieval failures;
- force model fallback;
- duplicate a background task;
- reproduce prompt injection test.

STOP.

---

## Step 9 — Discuss Checkpoint

When developer reports observations:

### ✅ What you interpreted correctly

### ⚠️ What you missed / misunderstood

### 🧠 Correct interpretation

Ask a follow-up if needed.

Do not create the learning note until the checkpoint is understood.

---

## Step 10 — Finish Lesson

After learning is complete:

1. write/update `docs/learning/<topic>.md`;
2. mark current lesson complete in `COURSE_PROGRESS.md`;
3. set next lesson from `COURSE.md` as current;
4. reset current-lesson state.

End with:

- what the developer should now be able to explain;
- 3–5 English interview questions;
- next lesson name.

Do not automatically begin the next lesson in the same turn unless asked.
