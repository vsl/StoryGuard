Да. Я бы относился к этому проекту **не как к “Codex строит мне pet-project”**, а как к лаборатории, где Codex — твой очень быстрый pair programmer, а твоя работа — **понимать architecture, проверять решения, ломать систему, смотреть traces и интерпретировать experiments**.

Главное правило такое:

> **Ты не обязан писать большую часть boilerplate-кода сам. Но ты обязан понимать, почему компонент существует, как через него идёт запрос, как он ломается и как мы доказали, что он работает.**

## Как выглядит один урок

Каждый урок из `COURSE.md` проходишь одним и тем же циклом:

```text
1. Understand
      ↓
2. Predict
      ↓
3. Codex implements
      ↓
4. Inspect
      ↓
5. Run / Break
      ↓
6. Measure
      ↓
7. Explain
      ↓
8. Next lesson
```

### 1. Understand — сначала понять задачу

Запускаешь:

```text
$storyguard-course-lesson

Continue with the next lesson from COURSE.md.
Do not code yet.

First explain:
- what problem we are solving;
- where this component sits in StoryGuard;
- the request/data flow;
- what I specifically need to understand for an AI Engineer interview.
```

На этом этапе **не надо уходить в документацию на два часа**.

Тебе нужно понять примерно:

```text
Что компонент делает?
Кто его вызывает?
Что он получает?
Что возвращает?
Почему мы не используем альтернативу?
```

Например для RabbitMQ:

```text
FastAPI
→ Taskiq
→ RabbitMQ
→ worker
```

и ты должен уже до кода понимать, зачем RabbitMQ находится посередине.

---

## 2. Predict — сначала сам предположи решение

Очень полезная часть.

До того как Codex реализует feature, попробуй сам сказать:

> «Я думаю, запрос будет идти вот так…»

Например:

```text
Upload manuscript
→ FastAPI
→ save metadata to PostgreSQL
→ file to MinIO
→ enqueue Taskiq task
→ RabbitMQ
→ worker
```

Даже если ошибёшься — прекрасно.

Потому что потом сравниваешь:

```text
моя mental model
vs
реальная implementation
```

Так архитектура запоминается намного лучше, чем если просто читать готовый код.

---

# 3. Codex implementation

После этого:

```text
$storyguard-course-lesson

I understand the architecture.
Implement the lesson.

Stay strictly inside this lesson.
Run tests.
Then stop before the developer checkpoint.
```

Codex пишет boilerplate, migrations, adapters, tests и т.д.

Ты **не обязан читать каждую строку**.

Это важный момент.

Если Codex сгенерировал 900 строк, бессмысленно сидеть и читать все 900.

Смотри прежде всего:

```text
entry point
interface
core implementation
data model
test
failure handling
```

Например для retrieval:

```text
Retriever interface
HybridRetriever
Elasticsearch query
Reranker call
retrieval tests
```

А всякие constructors/imports можешь читать гораздо поверхностнее.

---

# 4. Inspect — ты должен пройти запрос руками

После implementation попроси:

```text
Show me the exact code path for one real request.

Start from the API entry point and walk through:
file → function → function → external service → result.

Do not explain generic theory.
Use the actual StoryGuard code.
```

И сам открываешь эти файлы.

Например Story QA:

```text
POST /chat
    ↓
chat_service
    ↓
StoryQAGraph
    ↓
intent_router
    ↓
retriever
    ↓
Elasticsearch
    ↓
reranker
    ↓
LLM
    ↓
verifier
```

Если ты способен найти каждый из этих компонентов в repo — уже хорошо.

---

# 5. Run / Break — обязательно ломай систему

Это, пожалуй, один из самых важных элементов обучения.

Не только:

```text
works ✅
```

а:

```text
почему ломается?
что система делает при failure?
```

Например выключи Ollama.

И посмотри:

```text
local model
    X
LiteLLM
    ↓
OpenAI fallback
```

Или останови Elasticsearch.

И посмотри, какой failure получает retrieval.

Или специально отправь manuscript с:

```text
Ignore all previous instructions...
```

И проверь prompt injection protection.

Или дважды отправь один Taskiq job.

И смотри, появились ли duplicate facts.

Это и есть настоящий engineering experience.

---

# 6. Measure — AI feature без eval не считается завершённой

Вот тут используется второй важнейший skill:

```text
$storyguard-ai-experiment
```

Его вызываешь **каждый раз, когда меняется поведение AI**.

Например:

```text
BM25
→ vector
```

не:

> «Мне кажется vector лучше.»

А:

```text
$storyguard-ai-experiment

Compare vector retrieval against our existing BM25 baseline.

Use the same dataset.
Measure Recall@10, latency and failure cases.
Do not choose the winner for me.
```

Codex делает experiment.

А **вывод делаешь ты**.

Например результаты:

```text
             Recall@10   p95

BM25            .74      80ms
Vector          .81      130ms
```

Но потом смотришь failures и замечаешь:

```text
exact names
→ BM25 лучше

semantic questions
→ vector лучше
```

И твой вывод:

> «Ни один не подходит полностью → хочу попробовать hybrid.»

Вот здесь ты уже реально занимаешься AI engineering.

---

# Что такое AI Experiment Lab для тебя

Это будет твоя учебная лаборатория.

Вместо постоянного CLI:

```text
Dataset: NarrativeQA retrieval

Baseline:
BM25

Candidate:
Hybrid + reranker

[ Run ]
```

Получаешь:

```text
Recall
Citation support
Hallucinations
Latency
Cost
```

И смотришь failures.

Ты должен регулярно открывать эту страницу и задавать вопрос:

> **Почему Candidate изменил именно эти кейсы?**

Не просто смотреть на среднюю цифру.

---

# 7. LangSmith — использовать постоянно

После появления LangSmith я хочу, чтобы ты почти каждый AI lesson делал через trace.

Например вопрос:

> Why did Daniel stop trusting Laura?

Ты открываешь trace и сам находишь:

```text
intent
→ STORY_QA

complexity
→ MULTI_HOP

planner
→ 4 subquestions

query rewrite
→ ...

retrieval
→ 30 chunks

reranker
→ 6

generation
→ ...

verifier
→ supported
```

Вот это гораздо важнее, чем помнить API LangGraph наизусть.

На интервью тебя скорее спросят:

> «Почему система дала плохой ответ и как вы это дебажили?»

И ты должен уметь сказать:

> “I first inspected the trace to determine whether the failure came from routing, retrieval, reranking, or generation.”

---

# Когда использовать каждый skill

| Skill                             | Когда ты его вызываешь                                                               |
| --------------------------------- | ------------------------------------------------------------------------------------ |
| **`$storyguard-course-lesson`**   | Почти всегда. Основной способ идти по проекту                                        |
| **`$storyguard-feature`**         | Когда хочешь реализовать конкретную feature вне последовательного урока              |
| **`$storyguard-ai-experiment`**   | Любое изменение prompt/model/RAG/reranker/planner/HyDE/routing/verifier              |
| **`$storyguard-security-review`** | После features, связанных с RAG, tools, uploads, models, project boundaries, prompts |
| **`$storyguard-learning-review`** | Когда implementation уже есть и хочешь закрепить понимание                           |

То есть в обычной работе ты чаще всего используешь:

```text
course-lesson
```

А он по необходимости приводит к:

```text
feature
experiment
security review
learning review
```

---

# `$storyguard-feature`

Использовать отдельно, например:

```text
$storyguard-feature

Add filtering by chapter to the Continuity Issues endpoint.
```

Но **не используй его, чтобы обойти COURSE.md** и внезапно построить половину проекта.

Для основного обучения лучше course lesson.

---

# `$storyguard-security-review`

Не надо запускать после каждой кнопки.

Запускай после важных boundaries:

```text
manuscript ingestion

retrieval

tool routing

LLM routing

citations

project/version filtering

prompt handling
```

Например:

```text
$storyguard-security-review

Review the Story QA pipeline.

Focus on:
- indirect prompt injection;
- cross-project leakage;
- old manuscript version leakage;
- unauthorized tool use.
```

Твоя задача после этого — понять **хотя бы одну реальную атаку**.

Не просто:

> tests green.

А:

> «Вот malicious manuscript. Если бы мы передали его модели неправильно, она могла бы принять этот текст за instruction. Вот где мы проводим trust boundary.»

---

# `$storyguard-learning-review`

Используй **после сложного блока**, когда чувствуешь:

> «Codex всё сделал, но я пока не уверен, что смогу это объяснить.»

Например:

```text
$storyguard-learning-review

Teach me our model routing implementation.

Use actual StoryGuard code.
Then interview me.
```

Он должен разобрать:

```text
LangGraph
→ semantic alias
→ LiteLLM
→ Qwen
→ failure
→ OpenAI fallback
```

А потом дать вопросы на английском.

---

# Очень важное правило: иногда ты должен кодить сам

Не большие features.

Но маленькие изменения — обязательно.

Например после того, как Codex реализовал:

```text
max_retrieval_rounds = 2
```

сам поменяй на:

```text
3
```

запусти experiment и посмотри эффект.

Или самостоятельно:

```text
добавь новый query rewrite case
измени top_k
добавь test case
добавь prompt injection example
почини маленький bug
```

Тебе не нужно конкурировать с Codex по скорости написания FastAPI boilerplate.

Но **touching the system yourself (работать с системой руками)** очень важно.

---

# Что тебе не нужно учить наизусть

Не надо помнить:

```text
все аргументы Taskiq
весь API Elasticsearch
все методы LangGraph
весь LiteLLM config
```

На работе документация существует.

Ты должен помнить:

```text
когда это используется
почему
как устроено
какие failure modes
какие alternatives
```

Например:

### Elasticsearch

Не:

> «как называется 17-й параметр query DSL».

А:

> BM25 хорош для lexical/exact matching, vector — semantic, hybrid объединяет оба; reranker дороже, но точнее сортирует небольшой candidate set.

---

# Как понять, что урок можно закончить

Я бы использовал простой тест.

Ты должен без подсказки ответить на пять вопросов:

```text
1. What problem does this component solve?

2. Where is it in our architecture?

3. Why did we choose it over the main alternative?

4. How can it fail?

5. How do we know it works?
```

Например про reranker:

> **What problem?**
> First-stage retrieval has high recall but poor ordering.

> **Where?**
> Elasticsearch top 30 → cross-encoder → top 6.

> **Why?**
> Cross-encoder jointly evaluates query/document and is more accurate than embedding similarity, but too expensive for the whole corpus.

> **Failure?**
> Adds latency; may rerank badly if model/domain mismatch.

> **How know?**
> Compare Recall/Precision and downstream citation correctness plus latency.

Если можешь так ответить — идём дальше.

---

# Как будет выглядеть твоя неделя/сессия

Не обязательно «один lesson = один день».

Лучше каждая рабочая сессия:

```text
10–15 min
brief / architecture

30–90 min
Codex implementation + review

15–30 min
run / trace / experiment

10 min
ты объясняешь результат

5 min
learning note / English terms
```

Если Codex реализовал feature за 4 минуты — отлично.

**Не надо сразу бежать к следующей.**

Оставшееся время — как раз твоя учеба.

---

# И отдельный режим интервью

После каждых примерно 3–4 AI lessons я бы делал:

```text
$storyguard-learning-review

Interview me on everything implemented since the last review.

Ask questions in English.
Do not explain unless my answer is incomplete.
```

И вопросы вроде:

> Why did you choose hybrid retrieval?

> Why not only vector search?

> Why do you rerank only 30 candidates?

> What happens if your local model fails?

> How do you detect unsupported claims?

> How do you prevent prompt injection from retrieved documents?

Это очень хорошо связывает проект непосредственно с интервью.

---

# Самый главный принцип

Ты можешь позволить Codex написать **80–90% кода**.

Но нельзя позволять ему сделать за тебя эти четыре вещи:

```text
Architecture understanding

Failure diagnosis

Experiment interpretation

Engineering decision
```

Вот это должно оставаться твоим.

Codex:

> реализовал Hybrid RAG.

Ты:

> **почему Hybrid?**

Codex:

> запустил experiment.

Ты:

> **что означают результаты?**

Codex:

> нашёл 12 false positives.

Ты:

> **какой pattern у этих ошибок и что стоит менять?**

Codex:

> предложил три решения.

Ты:

> **какой trade-off мы выбираем и почему?**

Тогда в конце проекта StoryGuard будет не просто GitHub repo, сделанный AI. Он станет твоим **практическим курсом AI Engineering**.

### Mini glossary

* **pair programmer** — помощник, который пишет код вместе с тобой
* **mental model** — твоё внутреннее понимание устройства системы
* **vertical slice** — небольшая feature от входа до результата
* **failure mode** — способ, которым система может сломаться
* **baseline** — исходная версия для сравнения
* **candidate** — новая экспериментальная версия
* **trade-off** — компромисс между характеристиками
* **grounded answer** — ответ на основе реальных источников
* **failure analysis** — разбор причин ошибок
* **developer checkpoint** — действие, которое должен лично выполнить ты, прежде чем перейти дальше
