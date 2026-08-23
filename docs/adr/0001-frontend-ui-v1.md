# ADR 0001 — Evidence-first frontend v1

## Status

Accepted on 2026-08-23.

## Context

The repository had a single static Next.js landing page while the UI
specification defines a complete desktop-first product. FastAPI currently
publishes only project CRUD and health routes. The UI therefore needs to be
complete enough to exercise every specified workflow without inventing backend
state or implementing backend features in Next.js.

The reference image in the repository and `storyguard_ui_spec.md` establish an
editorial, calm, manuscript-oriented visual direction. The locked architecture
requires Next.js, React, TypeScript, Tailwind, TanStack Query, React Hook Form,
Zod, Lucide, Vitest, Testing Library, and Playwright.

## Decision

### Product structure

- Use the App Router route hierarchy from the UI specification.
- Keep a persistent project shell with left navigation, top bar, global search,
  and a collapsible contextual AI panel.
- Keep Search and Ask StoryGuard separate.
- Keep manuscript content read-only.
- Use URL query parameters for selected chapters, entities, issues, filters, and
  evidence deep links.
- Render unavailable, loading, empty, failure, abstention, and completed states
  explicitly.

### Rendering and state

- Route layouts and page wrappers remain Server Components.
- Interactive screens are isolated Client Components.
- TanStack Query owns server state and cache invalidation.
- React Hook Form and Zod own editable project forms and boundary validation.
- Temporary drawers, dialogs, filters, upload selection, and panel visibility
  stay in local React state.
- Developer Mode preference is local to the browser; it is not story data.
- No application-wide state library is introduced.

### API boundary

- The browser calls only same-origin `/api/*` URLs.
- Next.js rewrites those requests to the server-only `API_PROXY_TARGET`.
- This avoids local CORS coupling and keeps internal Docker service names out of
  browser bundles.
- All endpoint paths continue to belong to FastAPI. Next.js is a transport proxy,
  not a replacement backend.
- Project API responses are validated with Zod. Aggregate project-card fields are
  optional until FastAPI supplies them.
- Chat uses `fetch` streaming with a small SSE parser so POST bodies and named
  workflow events are supported.
- Background job state is polled only while a real job is queued or running.
- Upload percentage comes from native XHR progress events. Processing stages are
  never advanced by frontend timers.

### Missing APIs

- Do not ship runtime fixture data or a mock API mode.
- A missing route produces a distinct “waiting for its API” state.
- Keep the intended request wiring in place so a conforming backend response
  activates the UI without another redesign.
- Record every known backend gap in `docs/frontend-api-gaps.md`.

### Components and visual system

- Use CSS variables and Tailwind utilities for the paper, surface, ink, semantic
  severity, focus, and spacing system.
- Use Georgia only for editorial headings/manuscript copy and a system sans stack
  for application controls; this avoids a runtime font download.
- Use Lucide icons.
- Use native semantic elements and the native `<dialog>` primitive instead of
  adding Radix or shadcn packages.
- Severity always has a textual label and never relies on color alone.
- Render manuscript and model output as escaped React text. Do not accept
  arbitrary model HTML.

### Evidence and AI

- Evidence is represented by server-issued IDs and source coordinates.
- The reusable evidence drawer links to manuscript chapter/evidence query params.
- UI context may include a selected chapter, character, or issue, but explicit
  user text remains the chat request.
- Developer metadata may show routing, retrieval, model alias, latency, cost, and
  verification values returned by the server.
- Hidden chain-of-thought, prompts, credentials, and provider keys are never
  rendered.
- The Experiment Lab accepts only server-known datasets and configurations and
  has no automatic promotion action.

### Responsive and accessibility

- Desktop receives the full three-column workspace.
- On smaller screens the navigation and AI panel become overlays and evidence
  comparisons stack.
- Use semantic links/buttons, labels, visible focus rings, readable manuscript
  typography, native dialogs, reduced-motion support, and explicit live regions.

### Testing

- Vitest and Testing Library cover API/SSE behavior and evidence/entity-resolution
  components.
- Playwright covers the five critical workflows using network contract mocks.
- ESLint, Prettier, TypeScript production build, and Docker build remain required
  delivery checks.

## Alternatives

### Implement missing services in Next.js

Rejected. It would create a second backend, violate the FastAPI boundary, and
hide the actual course implementation work still required.

### Default runtime demo fixtures

Rejected. They could be mistaken for manuscript analysis and would allow fake
job progress or unsupported evidence to appear as real product state.

### Direct browser-to-FastAPI URL

Rejected. It requires local CORS changes and makes browser deployments depend on
host-visible backend origins.

### Global state store

Rejected. URL state, TanStack Query, and local state cover the present needs.

### shadcn/Radix component layer

Deferred. Native elements cover the v1 interactions with fewer dependencies.
Add a headless dialog/menu library only if measured accessibility or interaction
requirements exceed the native implementation.

## Why

This is the smallest implementation that keeps every product boundary honest:
the entire UI and its contracts exist now, working project operations remain
usable, and future backend lessons can activate features endpoint by endpoint.

## Consequences

- Most story-analysis pages currently show unavailable states against the real
  backend.
- Contract mocks are necessary for successful frontend integration and E2E tests
  until the corresponding FastAPI routes exist.
- FastAPI response shapes must be reconciled with the documented frontend
  contracts as endpoints are implemented.
- Runtime Markdown is deliberately unsupported; rich answer rendering should be
  added only with an approved sanitizer.

## Interview talking point

The frontend was built ahead of the AI pipeline without faking AI behavior. A
same-origin proxy, typed contracts, evidence IDs, explicit unavailable states,
and mocked contract tests separate product/UI progress from backend readiness.
