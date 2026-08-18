# StoryGuard

Evidence-first narrative consistency copilot and guided AI Engineering portfolio project.

Development follows [`COURSE.md`](COURSE.md) one lesson at a time. Architecture decisions are locked in the backend/AI and UI specifications under `docs/specs/`.

## Local infrastructure

Prerequisite: Docker Desktop or another Docker engine with Compose.

```bash
cp .env.example .env
docker compose up --build
```

Open:

- frontend: <http://localhost:3000>
- backend liveness: <http://localhost:8000/health/live>
- backend readiness: <http://localhost:8000/health/ready>
- RabbitMQ management: <http://localhost:15672>
- MinIO console: <http://localhost:9001>
- Elasticsearch: <http://localhost:9200>
- LiteLLM: <http://localhost:4000>

The default credentials are local-development values from `.env.example`. Do not reuse them outside local development or commit real provider secrets.

## Current scope

Lesson 0.2 provides only the local service skeleton and health boundaries. CRUD, manuscript ingestion, retrieval, and AI workflows arrive in later lessons.
