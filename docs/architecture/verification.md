# Documentation verification and diagram maintenance

[Guide index](README.md)

This page records the documentation work separately from historical application tests and AI evaluations. The architecture snapshot is dated **2026-09-16**.

## Checks performed for this update

Implementation reviewed at source revision `cbe826e`, before this documentation change.

- Validated 172 local links and Markdown anchors across the root README and 11 guide/maintenance pages.
- Rendered all nine Mermaid diagrams successfully with Mermaid CLI 11.12.0 and inspected the rendered images for readable labels and clipping.
- Exported three SVGs; checked valid XML, accessible titles/descriptions, absence of scripts/embedded HTML/external image references, and equality with renderer output.
- Checked 29 key source/configuration assertions, including retrieval constants, model names, search defaults, resolution limits, memory prompt, and course cursor.
- Checked the teaching example's character offsets and illustrative RRF calculation.
- Verified the documented Markdown-to-SVG output naming with the renderer.
- Ran `docker compose config --quiet` successfully; inspected the resolved service names without printing secret values.
- Ran `git diff --check` and Markdown whitespace/fence checks; confirmed changed files are limited to the root README and the architecture documentation directory.

These checks validate the documentation and its assets. They are not new application functionality tests, model-quality evidence, or proof that every clean-machine setup succeeds.

## Sources checked

Claims were checked against registered API routes, production frontend requests, worker lifecycles, validators, storage models, Dockerfiles, dependency manifests, and active model/gateway configuration. In particular:

- Current search API and UI enable reranking by default, despite the older lesson's optional-mode decision.
- Resolution uses the two-deployment Gemini pool, despite historical `gemma` names in pipeline/counter fields.
- GLiNER is selectable on upload, despite the original experiment's offline-only decision.
- Structured-memory repair can retain valid records from the second response; citation validity does not establish semantic support.
- Grounded QA and backend SSE chat remain unimplemented; current job progress uses polling.

Historical metrics were cross-checked with their linked reports. Framework terminology was checked with official documentation through Context7; repository configuration determines which capabilities StoryGuard actually uses.

## Reproduce the image exports

Editable sources are the Mermaid blocks in the Markdown pages. The exported images use [mermaid-config.json](diagrams/mermaid-config.json), Mermaid CLI **11.12.0**, white backgrounds, and SVG text labels. The CLI is a temporary documentation tool; it is not added to the frontend or backend dependencies.

With Node/npm and a working Chromium installation available, from the repository root:

```sh
render_dir=$(mktemp -d)
for page in system-overview embeddings-and-search models-and-gateway; do
  npx --yes --package @mermaid-js/mermaid-cli@11.12.0 mmdc \
    -i "docs/architecture/$page.md" \
    -o "$render_dir/$page.md" \
    -c docs/architecture/diagrams/mermaid-config.json -b white
  cp "$render_dir/$page-1.svg" "docs/architecture/diagrams/$page.svg"
done
```

The generated Markdown is only a temporary rendering output; do not replace the editable source pages with it. If using an already installed browser, set `PUPPETEER_SKIP_DOWNLOAD=true` during tool installation and supply `-p /path/to/puppeteer.json` with an `executablePath` appropriate to your machine. This update used installed Chrome in a temporary headless session. See [Mermaid CLI](https://github.com/mermaid-js/mermaid-cli) and [custom browser configuration](https://github.com/mermaid-js/mermaid-cli/blob/master/docs/already-installed-chromium.md).

Render the other Mermaid blocks when editing them, even though only three images are committed. Check both native size and the scaled GitHub-page view for readable labels, clipped text, and confusing edges. The three export sources include accessible titles and descriptions.

## Verification boundaries

This update changes documentation and diagram assets only. It does not change routes, schemas, prompts, models, configuration used by the application, or course progress.

No fresh application unit/integration suite, clean Docker build, live browser-to-worker smoke, model evaluation, or paid inference was run for this update. No new experiment or LangSmith trace IDs were created. Existing reports retain their original run scope. Learning notes were not rewritten, and no developer learning checkpoint was marked complete. The [interview guide](interview-guide.md#practice-checkpoint) provides a practice exercise without advancing the course.
