# StoryGuard — Frontend / UI Technical Specification

## 1. Purpose

StoryGuard is an AI-powered narrative consistency copilot for fiction writers.

The frontend must provide a clean desktop-first workspace where a writer can:

- create and manage story projects;
- upload and review manuscript versions;
- inspect parsed chapters and source text;
- browse the automatically generated Story Bible;
- inspect characters, locations, facts, events, and relationships;
- review possible continuity issues;
- ask AI questions about the current story;
- inspect evidence/citations behind AI answers;
- view analysis status and history;
- optionally inspect developer/debug metadata for AI workflows.

The UI is **not** a full manuscript editor. Manuscript content is read-only in v1.

The application must be fully containerized and runnable locally with Docker.

After startup, the frontend must be available in a browser at:

`http://localhost:3000`

---

# 2. Frontend Technology Stack

## Core

- **Next.js** — frontend framework
- **React**
- **TypeScript**
- **App Router**
- **Tailwind CSS** — styling
- **shadcn/ui** or equivalent headless component primitives
- **Lucide React** — icons

## Data / API

- native `fetch` or a small API client wrapper
- **TanStack Query** for server state, caching, loading/error states, background refetching
- **Zod** for runtime validation of API responses where useful

## Forms

- **React Hook Form**
- **Zod** validation

## Testing

- **Vitest** — unit tests
- **React Testing Library**
- **Playwright** — critical end-to-end flows

## Code Quality

- ESLint
- Prettier
- TypeScript strict mode

---

# 3. Runtime / Docker Requirements

The frontend must run inside Docker.

## Required local behavior

From the repository root:

```bash
docker compose up --build
```

The user must then be able to open:

```text
http://localhost:3000
```

and use the frontend.

## Frontend container

The frontend container must:

- install dependencies;
- build or run Next.js;
- listen on `0.0.0.0`;
- expose port `3000`;
- use environment variables for backend URL.

Example environment variable:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## Docker Compose expectation

Eventually the whole StoryGuard stack will contain:

```text
frontend
backend
worker
rabbitmq
postgres
elasticsearch
```

For the frontend phase, Docker Compose may initially run:

```text
frontend
mock-api
```

or:

```text
frontend
backend
```

depending on implementation order.

The frontend must never hard-code internal Docker service names in browser requests.

Browser-visible API requests must use a host-accessible URL such as:

```text
http://localhost:8000
```

or be proxied through Next.js.

---

# 4. UX / Visual Direction

The visual style should be:

- clean;
- minimal;
- editorial;
- professional;
- book-oriented;
- desktop-first;
- calm rather than flashy.

Avoid:

- neon gradients;
- excessive “AI” visual effects;
- glowing buttons;
- chat-first layouts everywhere;
- decorative animations that do not add product value.

Primary visual priorities:

1. manuscript text;
2. AI evidence;
3. citations;
4. continuity issue severity;
5. analysis status.

Suggested palette:

- off-white / white background;
- charcoal / dark slate text;
- muted green for healthy / valid;
- amber for possible issues;
- red-orange for likely issues;
- blue for informational states.

---

# 5. Application Information Architecture

Top-level routes:

```text
/projects
/projects/new

/projects/:projectId
/projects/:projectId/manuscript
/projects/:projectId/story-bible
/projects/:projectId/timeline
/projects/:projectId/issues
/projects/:projectId/ask
/projects/:projectId/analysis
/projects/:projectId/settings
```

Advanced routes:

```text
/projects/:projectId/check
/projects/:projectId/versions
/projects/:projectId/developer
```

---

# 6. Shared Project Layout

Inside a selected project, the application uses a persistent desktop layout.

```text
┌────────────────────────────────────────────────────────────┐
│ Top bar                                                    │
├──────────────┬──────────────────────────────┬───────────────┤
│ Sidebar      │ Main page                    │ AI panel      │
│              │                              │ optional      │
│ Overview     │                              │               │
│ Manuscript   │                              │               │
│ Story Bible  │                              │               │
│ Timeline     │                              │               │
│ Continuity   │                              │               │
│ Ask          │                              │               │
│ Analysis     │                              │               │
│ Settings     │                              │               │
└──────────────┴──────────────────────────────┴───────────────┘
```

## Left sidebar

Items:

```text
Overview
Manuscript
Story Bible
Timeline
Continuity
Ask StoryGuard
Analysis
Settings
```

Continuity may show an issue badge.

Example:

```text
Continuity   7
```

## Top bar

Must include:

- current project name;
- optional project switcher;
- global manuscript search;
- “Ask StoryGuard” button;
- current manuscript version.

Example:

```text
The Last Signal · v3
[ Search ] [ Ask StoryGuard ]
```

---

# 7. Global AI Panel

AI chat must not be limited to a single page.

A collapsible right-side panel should be available from key project pages.

Button:

```text
Ask StoryGuard
```

opens the panel.

The panel receives current UI context.

Examples:

From a character page:

```text
current_context:
type = character
entity_id = char_42
```

From manuscript:

```text
current_context:
type = chapter
chapter_id = chapter_17
```

From continuity issue:

```text
current_context:
type = issue
issue_id = issue_98
```

This context is supplied to the backend, but it must never silently override the explicit user question.

---

# 8. Page: Projects

Route:

```text
/projects
```

## Purpose

Show all story projects.

## UI

Header:

```text
StoryGuard
Your Stories
```

Primary action:

```text
+ New Story
```

Each project card displays:

- title;
- current manuscript version;
- chapter count;
- character count;
- continuity issue count;
- last analyzed date;
- analysis status.

Example:

```text
The Last Signal

Version: v3
42 chapters
17 characters
7 issues

Last analyzed:
17 Aug 2026
```

Card actions:

- Open
- Upload new version
- Delete project

## Empty state

```text
No stories yet.

Create your first story and upload a manuscript.
```

---

# 9. Page: Create Project

Route:

```text
/projects/new
```

## Fields

- Story title — required
- Description — optional
- Language — required

Supported languages should come from backend/config rather than hard-coded business logic.

Primary button:

```text
Create Story
```

After creation:

```text
Upload manuscript
```

---

# 10. Manuscript Upload

Supported formats in v1:

```text
.docx
.md
.txt
```

UI:

- drag-and-drop zone;
- file picker;
- filename;
- upload progress;
- validation errors.

After upload, frontend receives an asynchronous job identifier.

Example response:

```json
{
  "job_id": "job_123",
  "status": "queued"
}
```

Then show processing progress.

Example:

```text
Processing manuscript

✓ File uploaded
✓ Chapters detected
✓ Scenes extracted
● Building Story Bible
○ Creating embeddings
○ Indexing manuscript
○ Running continuity analysis
```

Progress must reflect real backend state.

Do not fake steps using timers.

---

# 11. Page: Overview / Dashboard

Route:

```text
/projects/:projectId
```

## Header

Show:

- story title;
- manuscript version;
- word count;
- last analysis time.

## Summary cards

```text
Characters
Locations
Events
Continuity Issues
```

Example:

```text
Characters      17
Locations       23
Events         148
Issues           7
```

## Continuity health

Display:

```text
3 likely issues
4 possible issues
```

Do not call issues “errors”.

Use:

```text
Likely issue
Possible issue
Needs review
```

## Analysis status

Example:

```text
Last analysis
Completed

42 / 42 chapters
```

Actions:

```text
Run analysis
View analysis
```

## Recent activity

Examples:

```text
New manuscript version uploaded
Continuity analysis completed
3 issues reviewed
```

---

# 12. Page: Manuscript

Route:

```text
/projects/:projectId/manuscript
```

Desktop layout:

```text
┌────────────────┬──────────────────────────────┬──────────────┐
│ Chapters       │ Manuscript                   │ AI Panel     │
│                │                              │ optional     │
└────────────────┴──────────────────────────────┴──────────────┘
```

## Chapter list

Show:

- chapter number;
- title;
- issue count;
- optional processing state.

Example:

```text
Chapter 1
Chapter 2    1
Chapter 3
Chapter 4    2
```

Search chapters.

## Main manuscript viewer

Read-only.

Must display:

- chapter title;
- scene boundaries if available;
- paragraph-level anchors;
- selected evidence highlighting.

The UI must support deep linking to evidence.

Example URL concept:

```text
/projects/123/manuscript?chapter=17&evidence=ev_456
```

The viewer should scroll to the relevant text and highlight it.

## Evidence indicator

Example:

```text
Evidence for Issue #41
```

Actions:

```text
Open evidence details
Ask StoryGuard about this
```

---

# 13. Story Bible

Route:

```text
/projects/:projectId/story-bible
```

Tabs:

```text
Characters
Locations
Objects
Relationships
Facts
Events
```

Each tab must support:

- search;
- filters where relevant;
- empty state;
- loading state;
- evidence navigation.

---

# 14. Story Bible: Characters

List:

```text
Daniel Reed
Laura Bennett
Emma Reed
John Hale
```

Selecting a character opens details.

## Character fields

Possible fields:

```text
Canonical name
Aliases
Role
Occupation
Age
Eye color
Lives in
First appearance
Relationships
```

Do not assume all fields exist.

Render only available facts.

## Key facts

Example:

```text
Served in the Coast Guard for 8 years
Survived the North Ridge incident
Does not trust easily
```

Each fact must provide:

```text
Show evidence
```

---

# 15. Entity Resolution UI

When StoryGuard detects possible duplicate entities:

```text
Possible duplicate characters

Daniel Reed
Mr. Reed

Confidence: 82%
```

Actions:

```text
Merge
Keep separate
Review evidence
```

This is a human-in-the-loop interface.

The frontend should preserve the backend-generated candidate pair and send user resolution back to the API.

---

# 16. Story Bible: Locations

Location details may include:

```text
Name
Type
Geographic description
Known properties
Events occurring here
Related characters
```

Example:

```text
Blackwood Manor

Type:
Estate

Known facts:
- Three floors
- Library on second floor
- East wing burned down in 1998
```

Each generated fact requires evidence.

---

# 17. Story Bible: Facts

Fact table/list.

Suggested columns:

```text
Subject
Predicate
Value
Confidence
Source
Status
```

Example:

```text
Daniel Reed | eye_color | green | High | Ch. 2 | Active
```

Allow filtering by:

- entity;
- fact type;
- chapter;
- confidence.

---

# 18. Story Bible: Events

Example:

```text
Daniel visited Paris
Summer 2018
Chapter 4
```

Fields may include:

```text
Participants
Location
Narrative position
Chronological time
Evidence
```

---

# 19. Timeline

Route:

```text
/projects/:projectId/timeline
```

Must distinguish:

```text
Narrative order
Chronological order
```

Example:

```text
2018
Daniel visits Paris

2021
Laura moves to London

March 2024
Sarah disappears
```

Each event should show:

```text
Narrative position:
Chapter 14

Chronological time:
Summer 2018
```

Filters:

- character;
- location;
- event type.

---

# 20. Continuity Issues

Route:

```text
/projects/:projectId/issues
```

## Filters

```text
Severity
Type
Status
Character
Chapter
```

Severity:

```text
Likely
Possible
Needs review
```

Types:

```text
Character attribute
Timeline
Relationship
Character knowledge
Object state
Location
World rule
Other
```

---

# 21. Issue Card

Example:

```text
Likely contradiction

Daniel's eye color appears inconsistent.

Chapter 2
"his green eyes..."

Chapter 17
"his blue eyes..."

Confidence: High
```

Actions:

```text
View
Valid issue
Not an issue
```

---

# 22. Issue Detail

Show:

```text
Current claim
Previous fact
Reason
Evidence A
Evidence B
Confidence
Issue type
Analysis run
```

Evidence should be visually comparable side-by-side where possible.

Example:

```text
Chapter 2
Green eyes

vs

Chapter 17
Blue eyes
```

Buttons:

```text
Open Chapter 2
Open Chapter 17
Valid issue
Not an issue
Add note
```

---

# 23. Feedback UI

If user selects:

```text
Not an issue
```

request a reason:

```text
Intentional contradiction
Character is lying
Flashback / timeline nuance
Wrong entity resolution
AI misunderstood context
Other
```

Optional free text:

```text
Sarah is wearing blue contact lenses here.
```

Feedback is later usable for evaluation.

---

# 24. Ask StoryGuard

Route:

```text
/projects/:projectId/ask
```

This is the full AI workspace.

## Input

```text
Ask anything about this story...
```

Example:

```text
Why did Daniel stop trusting Laura?
```

## Response

Answer must support:

- paragraphs;
- bullet points;
- inline citations;
- sources panel;
- uncertainty/abstention;
- follow-up questions.

Example:

```text
Daniel's distrust develops after several events:

1. Laura hides information about Sarah. [1]
2. She fails to meet him at the relay station. [2]
3. Daniel believes her decisions put the team at risk. [3]
```

---

# 25. Citation UI

Inline:

```text
Daniel first met Laura at the Harcourt party. [1]
```

Sources:

```text
[1] Chapter 4 · Scene 2
[2] Chapter 6 · Scene 1
```

Clicking a source opens an Evidence Drawer.

---

# 26. Evidence Drawer

Reusable component.

Must show:

- chapter;
- scene;
- paragraph/span;
- exact manuscript excerpt;
- related fact/claim;
- source manuscript version.

Action:

```text
Open in manuscript
```

---

# 27. AI Right-Side Panel

Available from:

```text
Overview
Manuscript
Story Bible
Timeline
Continuity
```

Not necessarily visible by default.

Example contextual question:

From manuscript:

```text
What does Daniel know at this point?
```

From character:

```text
When did Daniel first meet Laura?
```

From issue:

```text
Could this inconsistency be intentional?
```

---

# 28. Normal Search

Global project search is not the same as AI chat.

Search:

```text
Daniel Paris
```

Possible results:

```text
Characters
Daniel Reed

Locations
Paris

Events
Daniel visited Paris

Manuscript
Chapter 4 · 3 matches
```

This search should be optimized for fast direct retrieval.

---

# 29. Search vs Ask

Keep these as distinct UI concepts in v1:

```text
Search
Ask StoryGuard
```

Do not force one omnibox to guess user intent until there is a product reason to do so.

---

# 30. Check New Text

Advanced route:

```text
/projects/:projectId/check
```

UI:

```text
Paste new text
```

Example:

```text
Daniel stepped onto French soil for the first time.
```

Button:

```text
Check against story
```

Result:

```text
Possible continuity issue

Chapter 4 mentions Daniel visiting Paris in 2018.
```

---

# 31. Analysis Page

Route:

```text
/projects/:projectId/analysis
```

Show latest analysis run:

```text
Status
Completed

Chapters
42 / 42

Claims extracted
1482

Potential conflicts
31

Verified issues
7

Duration
4m 12s

Estimated LLM cost
$0.83
```

Also show current:

```text
manuscript_version
pipeline_version
model
retrieval_strategy
```

---

# 32. Analysis History

Example:

```text
v3 · Aug 17
7 issues

v2 · Aug 12
11 issues

v1 · Aug 3
9 issues
```

Allow opening a historical analysis.

Do not imply that an old result applies to the current manuscript.

---

# 33. Manuscript Version UI

Route or Settings subsection:

```text
/projects/:projectId/versions
```

Example:

```text
v3
Current

v2
Uploaded Aug 12

v1
Uploaded Aug 3
```

Actions in v1:

```text
View metadata
Delete old version
```

Optional later:

```text
Restore version
Compare versions
```

---

# 34. Upload New Version

Action:

```text
Upload new manuscript version
```

Before upload explain:

```text
StoryGuard will rebuild:

- Story Bible
- Search index
- Embeddings
- Continuity analysis
```

Old analysis history remains available.

---

# 35. Analysis / Job Progress

Long-running operations must have proper progress UI.

Possible states:

```text
queued
running
completed
failed
cancelled
```

Frontend may receive progress using:

- polling initially;
- SSE later / preferred for live progress.

Example UI:

```text
Processing Chapter 18 of 42
Extracting story facts
```

---

# 36. Error States

## LLM failure

```text
StoryGuard couldn't complete this request.

Retry
```

## Search unavailable

```text
Manuscript search is temporarily unavailable.
```

## Analysis failed

```text
Analysis failed at Chapter 14.

Retry analysis
```

## Insufficient evidence

Do not display as a technical error.

Display:

```text
I couldn't find enough evidence in the manuscript to answer this reliably.
```

---

# 37. Loading States

Avoid generic spinners where useful workflow state exists.

Examples:

```text
Understanding question...
Searching story...
Reranking evidence...
Verifying citations...
```

These labels must correspond to actual backend workflow states.

---

# 38. Empty States

Examples:

## Story Bible

```text
No Story Bible yet.

Upload a manuscript to extract characters, events, and facts.
```

## Continuity

```text
No analysis has been run yet.
```

## Ask

```text
Ask about characters, events, relationships, or anything in your manuscript.
```

---

# 39. Developer / AI Debug Mode

The product should include a developer mode for portfolio/demo use.

Toggle:

```text
Developer Mode
```

This must not expose private chain-of-thought.

It may show execution metadata:

```text
Intent
Question complexity
Planner used
Generated sub-questions
Queries generated
Retrieval strategy
Retrieved document count
Reranker scores
Tools called
Model
Token usage
Latency
Estimated cost
Verification result
```

Example:

```text
Intent:
STORY_QA

Complexity:
MULTI_HOP

Planner:
4 sub-questions

Retrieval:
Hybrid + reranker

Candidates:
30

Selected:
6

Citation verification:
Passed
```

---

# 39A. AI Experiment Lab

Developer Mode includes an internal AI Experiment Lab.

Suggested route:

```text
/projects/:projectId/developer/experiments
```

## Purpose

Run and compare real StoryGuard AI configurations without relying only on CLI scripts. This is internal developer tooling, not an end-user writer feature.

## Configuration panel

Display/select controlled server-known configurations for:

```text
Dataset
Baseline configuration
Candidate configuration
Retrieval strategy
Query rewriting
HyDE
Embedding configuration
Reranker
Prompt bundle
Model-routing configuration
Verifier
```

Primary action: `Run experiment`.

## Status

Show real background states: Queued, Running, Scoring, Completed, Failed.

## Results

Show baseline/candidate metrics including Retrieval Recall@10, Answer correctness, Citation support, Hallucination rate, p50/p95 latency, API cost, and Fallback rate when applicable.

## Failure browser

Allow filtering and inspecting retrieval misses, wrong routing, planner failures, unsupported answers, bad citations, continuity false positives/negatives, and model fallbacks. Expose safe LangSmith trace/run IDs when available.

The UI must not automatically promote an experiment candidate to the default configuration.

# 40. Reusable Frontend Components

Suggested component structure:

```text
components/
  layout/
    AppShell
    ProjectSidebar
    TopBar

  projects/
    ProjectCard
    CreateProjectForm

  manuscript/
    ChapterList
    ManuscriptViewer
    EvidenceHighlight

  story-bible/
    StoryBibleTabs
    EntityList
    CharacterDetails
    LocationDetails
    FactRow
    EventRow
    EntityResolutionCard

  continuity/
    IssueList
    IssueCard
    IssueDetail
    IssueEvidenceComparison
    IssueFeedbackDialog

  ai/
    AskInput
    ChatThread
    ChatMessage
    Citation
    SourcesPanel
    EvidenceDrawer
    AIPanel
    AgentActivity
    DeveloperDebugPanel

  analysis/
    AnalysisProgress
    AnalysisSummary
    AnalysisHistory
    VersionBadge

  developer/
    ExperimentLab
    ExperimentConfigPanel
    ExperimentComparison
    ExperimentMetricTable
    ExperimentFailureList
    ExperimentFailureDetail

  ui/
    Badge
    Button
    Dialog
    Drawer
    Tabs
    Select
    Table
    Tooltip
    Skeleton
```

---

# 41. Suggested Next.js App Router Structure

```text
app/
  layout.tsx
  page.tsx

  projects/
    page.tsx
    new/
      page.tsx

    [projectId]/
      layout.tsx
      page.tsx

      manuscript/
        page.tsx

      story-bible/
        page.tsx

      timeline/
        page.tsx

      issues/
        page.tsx

      ask/
        page.tsx

      analysis/
        page.tsx

      settings/
        page.tsx

      versions/
        page.tsx

      check/
        page.tsx
```

---

# 42. Frontend API Client Structure

Suggested:

```text
lib/
  api/
    client.ts
    projects.ts
    manuscripts.ts
    storyBible.ts
    continuity.ts
    chat.ts
    analysis.ts
    search.ts
```

Every API call should go through a shared client.

The client handles:

- base URL;
- JSON serialization;
- errors;
- optional auth token;
- request ID headers;
- standardized API errors.

---

# 43. API Contract — Projects

## List projects

```http
GET /api/projects
```

Response:

```json
[
  {
    "id": "project_1",
    "title": "The Last Signal",
    "current_manuscript_version": "v3",
    "chapter_count": 42,
    "character_count": 17,
    "issue_count": 7,
    "last_analyzed_at": "2026-08-17T10:00:00Z"
  }
]
```

## Create project

```http
POST /api/projects
```

Body:

```json
{
  "title": "The Last Signal",
  "description": "",
  "language": "en"
}
```

---

# 44. API Contract — Manuscripts

## Upload manuscript

```http
POST /api/projects/{projectId}/manuscripts
Content-Type: multipart/form-data
```

Response:

```json
{
  "manuscript_version_id": "mv_3",
  "version": "v3",
  "job_id": "job_123",
  "status": "queued"
}
```

## List chapters

```http
GET /api/projects/{projectId}/chapters
```

## Get chapter

```http
GET /api/projects/{projectId}/chapters/{chapterId}
```

Response must include paragraph or text-span identifiers sufficient for evidence deep links.

---

# 45. API Contract — Job Status

```http
GET /api/jobs/{jobId}
```

Response:

```json
{
  "id": "job_123",
  "status": "running",
  "stage": "extracting_story_facts",
  "progress": {
    "completed": 18,
    "total": 42
  }
}
```

Optional SSE endpoint:

```http
GET /api/jobs/{jobId}/events
```

---

# 46. API Contract — Story Bible

## Characters

```http
GET /api/projects/{projectId}/characters
```

## Character details

```http
GET /api/projects/{projectId}/characters/{characterId}
```

## Locations

```http
GET /api/projects/{projectId}/locations
```

## Facts

```http
GET /api/projects/{projectId}/facts
```

## Events

```http
GET /api/projects/{projectId}/events
```

All AI-extracted facts should expose evidence references.

---

# 47. Evidence Data Contract

Suggested reusable shape:

```json
{
  "id": "ev_123",
  "manuscript_version_id": "mv_3",
  "chapter_id": "chapter_17",
  "scene_id": "scene_2",
  "paragraph_id": "paragraph_88",
  "text": "His green eyes tracked the sweep of the beam...",
  "start_offset": 15,
  "end_offset": 63
}
```

Frontend should not infer source positions from text search alone.

---

# 48. API Contract — Continuity

## Issues list

```http
GET /api/projects/{projectId}/issues
```

Query params may include:

```text
severity
type
status
chapter_id
entity_id
```

## Issue detail

```http
GET /api/projects/{projectId}/issues/{issueId}
```

## Feedback

```http
POST /api/projects/{projectId}/issues/{issueId}/feedback
```

Body:

```json
{
  "verdict": "not_an_issue",
  "reason": "intentional_contradiction",
  "comment": "The character is deliberately lying."
}
```

---

# 49. API Contract — Ask StoryGuard

```http
POST /api/projects/{projectId}/chat
```

Body:

```json
{
  "message": "Why did Daniel stop trusting Laura?",
  "thread_id": "thread_1",
  "context": {
    "type": "project"
  }
}
```

Response may initially be synchronous for simple requests.

Preferred later behavior is streaming.

Suggested final response:

```json
{
  "message_id": "msg_22",
  "answer": "Daniel stopped trusting Laura after...",
  "citations": [
    {
      "index": 1,
      "evidence_id": "ev_123"
    }
  ],
  "metadata": {
    "intent": "STORY_QA",
    "complexity": "MULTI_HOP",
    "retrieval_strategy": "hybrid_reranker"
  }
}
```

---

# 50. API Contract — Search

```http
GET /api/projects/{projectId}/search?q=Daniel%20Paris
```

Response groups:

```json
{
  "characters": [],
  "locations": [],
  "events": [],
  "manuscript_matches": []
}
```

Normal search must remain separate from AI chat in v1.

---

# 51. API Contract — Analysis

## Start analysis

```http
POST /api/projects/{projectId}/analysis
```

Response:

```json
{
  "analysis_run_id": "run_55",
  "job_id": "job_998",
  "status": "queued"
}
```

## Analysis history

```http
GET /api/projects/{projectId}/analysis
```

## Analysis detail

```http
GET /api/projects/{projectId}/analysis/{runId}
```

---

# 52. Frontend State Strategy

Use:

- URL for navigation and selected resource where appropriate;
- TanStack Query for backend/server state;
- local React state for temporary UI state;
- avoid large global state libraries unless a concrete need appears.

Examples stored in URL:

```text
selected chapter
selected issue
filters
search query
```

Examples local:

```text
drawer open
dialog open
temporary form values
```

---

# 53. Accessibility

Requirements:

- keyboard accessible navigation;
- visible focus states;
- semantic buttons/links;
- sufficient color contrast;
- severity must not rely only on color;
- dialogs/drawers accessible;
- manuscript text readable at normal zoom.

---

# 54. Responsive Strategy

Priority:

```text
Desktop: full support
Tablet: supported
Mobile: basic support only
```

On smaller screens:

- sidebar collapses;
- AI panel becomes a full-height drawer;
- Story Bible tables become cards;
- evidence comparison stacks vertically.

This is a manuscript-oriented productivity tool, so mobile-first design is not required.

---

# 55. Frontend Security Requirements

Frontend must:

- treat manuscript content as data, never executable markup;
- sanitize/escape rendered user content;
- not render arbitrary HTML returned by LLM;
- not expose system prompts;
- not expose private backend credentials;
- never embed LLM/provider API keys in browser code;
- use backend for all privileged AI calls.

If rich text/markdown rendering is added later, sanitize output before rendering.

---

# 56. Testing Requirements

## Unit / Component

Test:

- issue cards;
- evidence drawer;
- citation rendering;
- entity resolution actions;
- analysis progress;
- empty/error/loading states.

## Integration

Test API-connected behavior with mocked backend.

## E2E critical flows

Playwright tests:

### Flow 1

```text
Open projects
→ create story
→ upload manuscript
→ see processing state
```

### Flow 2

```text
Open manuscript
→ select chapter
→ open evidence
```

### Flow 3

```text
Open continuity
→ open issue
→ mark Not an issue
```

### Flow 4

```text
Ask StoryGuard
→ receive answer
→ open citation evidence
```

### Flow 5

```text
Upload new manuscript version
→ see new processing job
```

---

# 57. Docker Deliverables

The frontend implementation must include:

```text
Dockerfile
docker-compose.yml
.dockerignore
.env.example
README.md
```

README must include:

```bash
docker compose up --build
```

Then:

```text
Open http://localhost:3000
```

The application must bind to:

```text
0.0.0.0:3000
```

not only `localhost` inside the container.

---

# 58. Suggested Frontend Dockerfile Requirements

Use a Node LTS image.

Prefer multi-stage build for production mode:

```text
dependencies
→ build
→ runtime
```

For local development, Docker Compose may run:

```bash
npm run dev -- --hostname 0.0.0.0
```

Production image should run:

```bash
npm run start
```

on port 3000.

---

# 59. Environment Variables

Minimum:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Optional future:

```env
NEXT_PUBLIC_ENABLE_DEVELOPER_MODE=true
NEXT_PUBLIC_APP_ENV=local
```

No secrets should use the `NEXT_PUBLIC_` prefix.

---

# 60. Definition of Done — Frontend v1

Frontend v1 is complete when:

- project list works;
- project creation works;
- manuscript upload works;
- background processing state is visible;
- overview page works;
- manuscript viewer works;
- Story Bible displays Characters, Locations, and Facts;
- Continuity page works;
- Ask StoryGuard page works;
- citations open evidence;
- right-side AI panel exists;
- analysis page works;
- settings page works;
- error/loading/empty states exist;
- Docker startup works;
- browser access works at `http://localhost:3000`;
- critical Playwright flows pass.

---

# 61. Important Product Constraint

The coding agent must not turn StoryGuard into:

- a full manuscript editor;
- a generic ChatGPT clone;
- a Grammarly replacement;
- a story generator;
- a multi-agent demo with no product justification.

The frontend should support the core product idea:

**StoryGuard protects story consistency and explains every important AI claim with evidence from the manuscript.**

