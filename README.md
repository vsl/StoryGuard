# StoryGuard Codex Course Pack v2

This is the course/control layer for an existing StoryGuard repository.

## Frontend

StoryGuard now includes the complete evidence-first frontend shell described in
`docs/specs/storyguard_ui_spec.md`. It provides project CRUD, manuscript and
Story Bible views, continuity review, contextual AI chat, analysis/version
screens, settings, and the internal AI Experiment Lab.

Start the local stack:

```bash
docker compose up --build
```

Then open:

```text
http://localhost:3000
```

Browser API calls stay same-origin. Next.js proxies `/api/*` to
`API_PROXY_TARGET` (`http://backend:8000` in Compose), so internal Docker names
and backend credentials are never sent to the browser.

The current backend implements project CRUD only. UI features whose endpoints
do not exist show an explicit unavailable state; they do not display invented
data or simulated progress. See `docs/frontend-api-gaps.md`.

Frontend checks:

```bash
cd frontend
npm test
npm run lint
npm run build
npm run test:e2e
```

## Your current position

Already completed:

```text
Lesson 0.1 — System boundaries
Lesson 0.2 — Docker/local architecture
```

Next:

```text
Lesson 1.1 — FastAPI + PostgreSQL
```

## Normal command

You only need:

```text
$storyguard-course-lesson
```

No long prompt.

Codex will read `COURSE_PROGRESS.md` and continue automatically.

## Core behavior

Codex must:

```text
ask
→ wait for your answer
→ discuss what is right/wrong
→ show correct mental model
→ propose implementation
→ ask for approval
→ only then write code
```

## Included

- `AGENTS.md`
- `COURSE.md`
- `COURSE_PROGRESS.md`
- `CODEX_WORKFLOW.md`
- `USER_COMMANDS.md`
- five StoryGuard skills
- nested backend/AI/frontend instructions
- `.codex/config.toml`
- `.codex/rules/safety.rules`
- backend/UI specifications
- Hugging Face dataset strategy
- model/dataset config examples
- learning/experiment/ADR templates
- guide for applying to existing repository

See:

```text
APPLY_TO_EXISTING_REPO.md
```
