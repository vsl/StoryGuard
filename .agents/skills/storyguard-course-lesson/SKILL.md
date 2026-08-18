---
name: storyguard-course-lesson
description: Run StoryGuard development as a guided AI Engineer course lesson. Use when implementing the next course module or when the developer asks to continue the StoryGuard course. Codex writes implementation code, but each lesson requires developer checkpoints, experiments, debugging, and interview understanding.
---

# StoryGuard Course Lesson

Read root `AGENTS.md`, `COURSE.md`, relevant specs, and the prior learning note if applicable.

## 1. Identify the lesson
State lesson number/name, prerequisites, product outcome, and AI Engineering concept. Do not implement future lessons unless strictly required.

## 2. Brief before coding
Give a concise architecture briefing in Russian with important English terms + translations. Explain the problem and data/request flow.

## 3. Two definitions of done
### Codex implementation criteria
What code/tests/evals must exist.
### Developer learning criteria
What the developer must personally inspect, run, explain, debug, or decide.

## 4. Implement
Use relevant StoryGuard specialist skills. Keep the slice focused.

## 5. Verify
Run tests, Docker smoke checks, AI experiments, and/or security tests appropriate to the lesson.

## 6. Developer checkpoint
STOP and give a concrete hands-on task. Examples: inspect a LangSmith trace, interpret metrics, diagnose a retrieval miss, choose baseline vs candidate, reproduce a retry, explain a routing decision. Do not make the lesson's learning decision for the developer.

## 7. Learning artifact
After the checkpoint, update `docs/learning/<lesson-topic>.md` with actual code paths, traces, metrics, failures, trade-offs, and interview questions.

## 8. Finish
Report implementation status, tests/evals, checkpoint status, what the developer can now explain, and next lesson.
