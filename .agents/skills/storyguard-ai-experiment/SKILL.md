---
name: storyguard-ai-experiment
description: Change or evaluate StoryGuard AI behavior. Use for prompts, models, LiteLLM routing, retrieval, embeddings, chunking, reranking, planner, query rewriting, HyDE, tool routing, hallucination mitigation, verifier, abstention, or continuity quality.
---

# StoryGuard AI Experiment

1. Define one falsifiable hypothesis. Do not bundle unrelated AI changes.
2. Capture baseline: code SHA, dataset/version, prompt versions, model aliases/resolved models, LiteLLM config, embedding/reranker, chunking/retrieval, budgets.
3. Run baseline on the SAME dataset as candidate.
4. Record relevant quality + latency + cost metrics. Core metrics include Retrieval Recall@K, answer correctness, citation validity/support, hallucination rate, continuity precision/recall/F1, abstention, routing, p50/p95, API cost, fallback rate.
5. Make one candidate change while preserving baseline config.
6. Run LangSmith dataset/experiment where applicable and capture IDs.
7. Inspect representative failures, not only aggregate metrics.
8. Report baseline vs candidate, regressions, latency/cost, failure-mode changes, and recommendation.
9. Do not promote a candidate because one example looks better.
10. Save `docs/experiments/YYYY-MM-DD-<name>.md` and update the learning note.

The developer should personally interpret the result when this experiment is part of a course lesson.
