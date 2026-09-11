# StoryGuard Codex Course Pack v2

This is the course/control layer for an existing StoryGuard repository.

## Project scope

StoryGuard is a personal, non-commercial AI Engineering portfolio and learning
project, with no production deployment or planned sale. Non-commercial models
and datasets are acceptable; retain attribution, provenance, and license terms.
Revisit licensing suitability only if this intended use changes.

The [focused course](COURSE.md) targets one complete portfolio flow: upload a
manuscript, browse Story Bible, ask questions with real citations, and review
possible character-attribute contradictions. Nine core lessons remain after
Lesson 5.3's pending learning checkpoint; this curriculum revision does not
complete that checkpoint or implement those features.

Reuse the existing retrieval, tracing, Experiment Lab, story memory, and model
gateway. Bounded planning, evaluations, grounding, and reliability remain core.
Query rewriting and HyDE are optional experiments. Broader continuity,
product-help chat, checking pasted text, and advanced version management are
deferred. Cloud deployment is an optional later capstone and remains an interview
skills gap until completed. The existing stack and promoted models are unchanged.

Supported story entities: characters/people, facilities/buildings, countries
and settlements, natural/geographical locations, organizations, and vehicles.
General items/artifacts and a catch-all category are outside current scope.
These are product categories, independent of the selected model or dataset.
Entity resolution defaults to xCoRe + Gemma: supported exact-span coreference
links skip Gemma; remaining candidate pairs use Gemma. Automatic merging stays
on. Qwen comparison is deferred. This is a developer-approved speed-oriented
promotion with known wrong-merge risk, not demonstrated full-book accuracy.

The worker image includes an isolated coreference runtime. Rebuild with
`docker compose up -d --build backend worker frontend`, then use **Resolve
entities** or **Resume resolution** in Story Bible. Completed coreference output
is cached per manuscript version; Stop kills an unfinished scan. The UI shows
the combined pipeline, merges applied without Gemma, and pairs sent to Gemma.
Coreference failures visibly fall back to Gemma. Set
`models.llms.entity_resolution.pipeline: gemma` in `config/models.yaml` and
restart backend/worker to roll back routing; existing decisions are not undone.

The Docker application database contains disposable test data and may be
explicitly reset for this iteration. Do not infer permission to wipe unrelated
databases, Docker volumes, original source files, or model caches.

## Frontend

StoryGuard now includes the complete evidence-first frontend shell described in
`docs/specs/storyguard_ui_spec.md`. It provides project CRUD, manuscript and
Story Bible views, continuity review, contextual AI chat, analysis/version
screens, settings, and the internal AI Experiment Lab.

Start the currently implemented application slice:

```bash
docker compose up -d --build frontend worker
```

Compose starts their PostgreSQL, MinIO, RabbitMQ, Elasticsearch, and backend
dependencies. LiteLLM is already used by extraction and resolution; Lesson 6.1
extends that integration with a local/API comparison and bounded fallback.

Then open:

```text
http://localhost:3000
```

Browser API calls stay same-origin. Next.js proxies `/api/*` to
`API_PROXY_TARGET` (`http://backend:8000` in Compose), so internal Docker names
and backend credentials are never sent to the browser.

The backend implements project CRUD plus the real manuscript upload, version,
job progress, parsing/BM25/vector ingestion, and chapter-reading vertical slice. Later
UI capabilities whose endpoints do not exist show an explicit unavailable
state. See `docs/frontend-api-gaps.md`.

## LangSmith tracing

Tracing is disabled by default and search still works when LangSmith is absent.

1. Sign in at [smith.langchain.com](https://smith.langchain.com/), open
   **Settings → API Keys**, and create a key. Copy it immediately; LangSmith does
   not show the value again.
2. Put the key in the repository's untracked `.env` file, not `.env.example`:

   ```dotenv
   LANGSMITH_API_KEY=your-key
   LANGSMITH_ENDPOINT=https://api.smith.langchain.com
   LANGSMITH_PROJECT=storyguard-local
   LANGSMITH_TRACE_CONTENT=minimal
   LANGSMITH_TRACING=true
   ```

   For an EU LangSmith workspace, use
   `https://eu.api.smith.langchain.com` as the endpoint.
3. Rebuild the services so the pinned SDK and environment are loaded:

   ```bash
   docker compose up -d --build backend worker frontend
   ```
4. Upload and finish processing a manuscript, then run either search path:

   - UI: open a project, click **Search**, choose whether to use the reranker,
     and submit a query.
   - Swagger: open [localhost:8000/docs](http://localhost:8000/docs), expand
     `GET /api/projects/{project_id}/search`, enter the project UUID and query,
     set `rerank`, then click **Execute**.
5. Open [LangSmith](https://smith.langchain.com/), select **Tracing Projects →
   storyguard-local**, and open the newest `retrieve_hybrid` or
   `retrieve_hybrid_reranked` trace. The reranked trace should contain parallel
   `retrieve_bm25` and `retrieve_vector` spans, followed by `rrf_fusion` and
   `reranker`. With `rerank=false`, the `reranker` span is absent.

`LANGSMITH_TRACE_CONTENT` controls external trace content:

- `minimal` (default): hashed IDs, counts, scores, versions, parameters, and
  timings; no query or manuscript text.
- `redacted`: the same diagnostics plus content-shaped fields replaced by
  `<redacted:N chars>`.
- `full`: raw queries and retrieved chunks. Use only as an explicit opt-in for
  public or synthetic manuscripts.

Frontend checks:

```bash
cd frontend
npm test
npm run lint
npm run build
npm run test:e2e
```

## Your current position

See `COURSE_PROGRESS.md`, the authoritative course cursor.

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
