# How to Use Codex on StoryGuard

Do NOT ask Codex to “build StoryGuard from the specs.” The project is developed lesson-by-lesson so Codex can write quickly while the developer still learns the system.

## Preferred course workflow
```text
$storyguard-course-lesson
Continue with the next lesson from COURSE.md.
Do not implement later lessons.
Before coding, tell me what I need to understand.
After coding, stop at the developer checkpoint instead of interpreting the result for me.
```

## Normal feature slice
```text
$storyguard-feature
Implement manuscript upload through FastAPI -> MinIO -> manuscript_versions/job_runs -> Taskiq enqueue. Follow specs. Do not implement parsing yet. Before coding show acceptance criteria and affected components.
```

## AI experiment
```text
$storyguard-ai-experiment
Compare vector retrieval with the current BM25 baseline on the same retrieval eval set. Do not promote the candidate. Record Recall@10, p50/p95 latency, and failure examples.
```

## Security review
```text
$storyguard-security-review
Review Story QA retrieval for prompt injection, cross-project retrieval, old-version leakage, and hallucinated evidence IDs. Add regression tests.
```

## Learning review
```text
$storyguard-learning-review
Teach me how our retrieval fallback works using the actual code, tests, metrics, and LangSmith trace. Give 5 English interview questions and one manual debugging task.
```

## Manual checkpoints the developer must personally do
- inspect LangSmith traces;
- diagnose retrieval failures;
- interpret retrieval strategy experiments;
- compare local vs API model routing;
- inspect prompt-injection tests;
- explain an abstention;
- reproduce a retry/idempotency failure;
- present the architecture without reading the spec.
