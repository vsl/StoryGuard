# Lesson 0.2 — Docker local system

## Status

- Implementation checkpoint: complete.
- Developer checkpoint: complete. Elasticsearch was stopped, the failure boundary was predicted, observed, and recovered.

## Problem

StoryGuard needs one reproducible local system whose services start in dependency order, persist data, and expose failures without confusing a running process with a ready application.

## Selected design

`compose.yaml` runs the locked local architecture: Next.js, FastAPI, PostgreSQL, MinIO, Elasticsearch, RabbitMQ, a Taskiq worker, and LiteLLM. Compose health checks control startup dependencies. Named volumes persist PostgreSQL, MinIO, and Elasticsearch data.

FastAPI exposes two different health boundaries in `backend/app/main.py`:

- `GET /health/live` answers whether the API process is alive.
- `GET /health/ready` checks PostgreSQL, MinIO, and Elasticsearch concurrently and returns `200` only when all are reachable; otherwise it returns `503` with per-service state.

The pure status mapping lives in `backend/app/health.py` and is covered by `backend/tests/test_health.py`.

## Why this design

Docker Compose is the smallest tool that reproduces the required multi-service development environment. Liveness and readiness are separate because restarting a healthy FastAPI process cannot repair an unavailable Elasticsearch dependency. Named volumes let containers be stopped or recreated without treating container lifetime as data lifetime.

## Alternatives rejected

- Starting every service manually: less reproducible and harder to debug.
- One health endpoint: hides the difference between process failure and dependency failure.
- Container-local database/index storage: data disappears when the container is replaced.
- Kubernetes: unnecessary orchestration for this local course stage.

## Startup and request flow

```text
PostgreSQL + MinIO + Elasticsearch become healthy
  -> FastAPI starts and becomes live
  -> Next.js starts

RabbitMQ becomes healthy
  -> Taskiq worker starts and waits for jobs

Browser -> Next.js :3000
Browser/API client -> FastAPI :8000 -> dependency checks
```

`depends_on` protects initial startup ordering. It does not prevent a dependency from failing later, so runtime readiness checks remain necessary.

## Failure and debugging examples

### PostgreSQL 18 volume layout

The first Compose run failed because `postgres:18.4-alpine3.24` was mounted at the older `/var/lib/postgresql/data` path. PostgreSQL 18 expects the persistent parent directory `/var/lib/postgresql`, allowing its major-version-specific data directory below it. The existing Docker volume was inspected and found empty, then `compose.yaml` was corrected without deleting any volume.

### Elasticsearch outage checkpoint

The developer stopped Elasticsearch and observed:

```http
HTTP/1.1 503 Service Unavailable

{"status":"not_ready","checks":{"postgres":"up","minio":"up","elasticsearch":"down"}}
```

FastAPI remained live because its process was healthy, but StoryGuard was not ready for functionality requiring retrieval. This is `503 Service Unavailable`, not `403 Forbidden`: availability failed, not authorization. The current static Next.js page remained available because it did not need Elasticsearch for that request.

Elasticsearch uses `elasticsearch_data:/usr/share/elasticsearch/data`, so `docker compose stop` followed by `docker compose start` preserves indexed data. `docker compose down -v` would intentionally remove named volumes and must not be used when the data should survive.

After `docker compose start elasticsearch`, Elasticsearch returned to `healthy` and readiness recovered to:

```http
HTTP/1.1 200 OK

{"status":"ready","checks":{"postgres":"up","minio":"up","elasticsearch":"up"}}
```

## Traces, metrics, latency, and cost

- LangSmith trace/run IDs: not applicable; no AI workflow runs in this lesson.
- Evaluation metrics: not applicable.
- Model cost: zero; no LLM requests were made.
- Local resource trade-off: Elasticsearch is limited to a 512 MB JVM heap in `compose.yaml`, which lowers development memory use but is not a production sizing decision.
- Readiness checks run concurrently with two-second client timeouts, avoiding serial dependency-wait latency.

## Developer checkpoint result

The developer correctly explained that FastAPI can continue running when Elasticsearch stops and that Elasticsearch persistence depends on a mounted volume. The experiment established the remaining distinction: a dependency outage produces readiness `503`, while `403` represents an authorization refusal.

## Interview questions

1. **What is the difference between liveness and readiness?**
   - Liveness says the process is running; readiness says the application can currently serve dependency-backed work.
2. **Why did the Elasticsearch outage return 503 instead of 403?**
   - `503` reports temporary service unavailability; `403` means an authenticated or identified caller is not authorized.
3. **Does stopping an Elasticsearch container delete its data?**
   - No when a named volume is mounted. Stop/start preserves it; removing the volume intentionally deletes it.
4. **Why did FastAPI remain live while readiness failed?**
   - Its event loop and HTTP server still worked, but one dependency required for full service was unavailable.
5. **What does Compose `depends_on: condition: service_healthy` guarantee?**
   - It gates initial dependent startup; it does not provide runtime failover or keep dependencies healthy afterward.

## Learning review: `service_healthy`

`healthcheck` is a command that Docker runs inside a container. Exit code `0` means the container is `healthy`; a non-zero exit code means the check failed. `condition: service_healthy` in `depends_on` tells Compose to start a dependent service only after the dependency has passed its healthcheck.

In this project:

| Dependent | Waits for a healthy service |
|---|---|
| `backend` | `postgres`, `minio`, `elasticsearch` |
| `frontend` | `backend` |
| `worker` | `rabbitmq` |

This is an **initial startup gate**, not continuous monitoring or automatic failover. If Elasticsearch becomes unhealthy after `backend` has started, Compose does not automatically stop or restart `backend`. FastAPI's `/health/ready` catches that runtime outage and returns `503`.

One important implementation detail: the backend Compose healthcheck calls `/health/live`, so it verifies that the Uvicorn process responds. The application-level `/health/ready` separately verifies PostgreSQL, MinIO, and Elasticsearch for dependency-backed work. This is why a running backend can be Compose-healthy while readiness is `503`.

### Hands-on exercise

Run `docker compose stop elasticsearch`, then `docker compose ps` and curl both `/health/live` and `/health/ready`. Explain which result is controlled by Docker's healthcheck and which result is controlled by StoryGuard's FastAPI code. Start Elasticsearch again and verify readiness returns `200`.
