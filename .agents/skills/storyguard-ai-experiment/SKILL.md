---
name: storyguard-ai-experiment
description: Design and run StoryGuard AI experiments. Use for prompt/model/routing/retrieval/embedding/reranker/planner/HyDE/verifier/abstention/continuity changes. Developer predicts and interprets results before candidate promotion.
---

# StoryGuard AI Experiment

## 1. Explain the variable

In chat explain:
- baseline;
- candidate idea;
- why it could improve;
- what could regress;
- relevant metrics.

Ask:

```text
What do you predict will improve, and what might get worse?
```

STOP.

## 2. Discuss Prediction

When developer answers:

### ✅ Correct prediction
### ⚠️ Missing / incorrect assumptions
### 🧠 Trade-off model to remember

## 3. Propose Experiment Plan

Show:
- same dataset/version;
- baseline config;
- candidate config;
- metrics;
- latency/cost;
- failure categories;
- LangSmith experiment/traces.

Ask:

```text
Approve this experiment plan?
```

STOP.

## 4. Run After Approval

Run baseline and candidate.

Preserve versions/config.

## 5. Show Results — Do Not Choose Winner

Show:

- quality metrics;
- latency;
- cost;
- fallback rate;
- representative failure examples.

Ask:

```text
What do you conclude?
Keep baseline, promote candidate, or run another experiment?
```

STOP.

## 6. Discuss Conclusion

Correct/extend the developer's interpretation.

Only after explicit developer decision may the primary baseline be changed.

## 7. Save Report

Write `docs/experiments/...` only after result interpretation/decision is discussed.

If the experiment is part of the current course lesson, update learning/progress only after the course checkpoint is complete.
