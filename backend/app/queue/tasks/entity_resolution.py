import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from collections import deque
from datetime import datetime, timezone

import httpx
from langsmith import traceable

from app.ai.coreference import MODEL as COREFERENCE_MODEL, REVISION as COREFERENCE_REVISION, cluster_membership, load_coreference
from app.ai.entity_resolution import EntityResolutionError, ResolutionOutput, ResolutionResult, resolve_pair
from app.ai.tracing import annotate_trace
from app.db.models.entity_resolution import ResolutionCandidate
from app.db.models.job_run import JobRun
from app.db.session import SessionLocal
from app.entity_resolution import (
    MAX_CALLS_PER_RUN, RUN_BUDGET_SECONDS, ResolutionConflict,
    apply_automatic_predictions, candidates_for, current_scope, make_pair,
    needs_evaluation, prepare_candidates, resolution_config, resolution_counts,
    save_prediction, source_rows,
)
from app.queue.broker import broker
from app.queue.tasks.ingestion import _finish_stage, _start_stage

logger = logging.getLogger(__name__)
CANCEL_POLL_SECONDS = 1
PROVIDER_RETRY_DELAY_SECONDS = 5


class ResolutionStopped(Exception):
    pass


def owns_run(job: JobRun | None, attempt: int) -> bool:
    # The attempt fences off old responses after Stop -> Resume.
    return job is not None and job.status == "running" and job.attempts == attempt


def require_run(job: JobRun | None, attempt: int) -> None:
    if not owns_run(job, attempt):
        raise ResolutionStopped("user_stopped" if job and job.status == "cancelled" else "run_superseded")


def trace_counts(candidates) -> dict:
    return {**resolution_counts(candidates),
            "merge_decisions_applied": sum(item.applied_decision == "merge" for item in candidates),
            "separate_decisions_applied": sum(item.applied_decision == "keep_separate" for item in candidates)}


async def _fail(job_id: uuid.UUID, code: str, attempt: int | None) -> None:
    async with SessionLocal() as session, session.begin():
        job = await session.get(JobRun, job_id, with_for_update=True)
        if job is None or (not owns_run(job, attempt) if attempt is not None else job.status != "queued"):
            return
        now = datetime.now(timezone.utc)
        _finish_stage(job, now)
        job.status = "failed"
        job.error_code = code
        job.error_message_safe = {
            "RESOLUTION_SCOPE_CHANGED": "The manuscript changed during resolution. Refresh and try again.",
        }.get(code, "Entity resolution could not be completed. Existing decisions were preserved.")
        job.completed_at = now


async def _resolve_with_stop(pair, client, job_id, attempt, timeout, diagnostics):
    task = asyncio.create_task(resolve_pair(pair, client, request_timeout=timeout, diagnostics=diagnostics))
    deadline = asyncio.timeout(2 * timeout)
    try:
        async with deadline:
            while True:
                done, _ = await asyncio.wait({task}, timeout=CANCEL_POLL_SECONDS)
                async with SessionLocal() as session:
                    job = await session.get(JobRun, job_id)
                    require_run(job, attempt)
                if done:
                    return await task
    except TimeoutError:
        diagnostics["timeout_seconds"] = 2 * timeout if deadline.expired() else timeout
        raise
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@traceable(
    name="entity_resolution_batch", run_type="chain",
    process_inputs=lambda inputs: {"job_id": str(inputs["job_id"])},
    process_outputs=lambda _: {},
    # Controlled error codes are attached below; never trace raw DB/queue errors.
    exceptions_to_handle=(Exception, asyncio.CancelledError),
)
async def run_resolution_job(job_id: uuid.UUID) -> None:
    batch_started = time.monotonic()
    summary = {"outcome": "ignored", "end_reason": "job_not_queued", "batch_number": None,
               "gemma_attempts": 0, "coreference_shortcuts": 0, "retry_attempts": 0,
               "failed_attempts": 0, "continuation_queued": False}
    batch_trace_id = annotate_trace(metadata={"job_id": str(job_id), "component": "entity_resolution"})
    started = time.monotonic()
    attempt = None
    retry_pending = False
    try:
        async with SessionLocal() as session, session.begin():
            job = await session.get(JobRun, job_id)
            if job is None or job.job_type != "entity_resolution" or job.status != "queued":
                return
            project_id, version_id = job.project_id, job.manuscript_version_id
            await current_scope(session, project_id, version_id, lock=True)
            await session.refresh(job, with_for_update=True)
            if job.status != "queued":
                return
            job.status = "running"
            job.attempts += 1
            attempt = job.attempts
            summary.update(outcome="running", end_reason="in_progress", batch_number=attempt)
            config = resolution_config()
            annotate_trace(metadata={"job_id": str(job_id), "batch_number": attempt,
                "project_id": str(project_id), "manuscript_version_id": str(version_id),
                "pipeline": config.get("pipeline", "gemma"), "auto_apply": config.get("auto_apply") is True,
                "max_gemma_attempts": MAX_CALLS_PER_RUN, "batch_budget_seconds": RUN_BUDGET_SECONDS})
            now = datetime.now(timezone.utc)
            job.started_at = job.started_at or now
            _start_stage(job, "resolution_candidates", now)
            await prepare_candidates(session, version_id)
            # Apply saved decisions from older/stopped runs before any new inference.
            await apply_automatic_predictions(session, version_id)
            candidates = await candidates_for(session, version_id)
            initial_totals = trace_counts(candidates)
            pending = [item for item in candidates if needs_evaluation(item)]
            pending.sort(key=lambda item: bool(item.error_code))
            pending_ids = deque(item.id for item in pending)
            job.total_units = len(candidates)
            job.completed_units = sum(bool(item.llm_decision or item.applied_decision or item.error_code) for item in candidates)
            sources = {mention.id: (mention, chapter) for mention, chapter in await source_rows(session, version_id)}
            combined = resolution_config().get("pipeline") == "coreference_gemma"
            _start_stage(job, "coreference" if combined and pending_ids else "entity_resolution", datetime.now(timezone.utc))

        summary["version_totals"] = initial_totals
        linked = {}
        coreference_hashes = {}
        coreference_metadata = {}
        coreference_error = None
        if combined and pending_ids:
            async def check_running():
                async with SessionLocal() as session:
                    require_run(await session.get(JobRun, job_id), attempt)
                    await current_scope(session, project_id, version_id)

            chapters = {str(chapter.id): chapter for _, chapter in sources.values()}
            documents = [{"id": key, "text": chapter.text} for key, chapter in chapters.items()]
            try:
                cache = await load_coreference(version_id, documents, check_running)
                summary["coreference_cache_hit"] = cache.get("cache_hit")
                summary["coreference_scan_trace_id"] = cache.get("trace_id")
                coreference_hashes = {doc["id"]: doc["text_sha256"] for doc in cache["documents"]}
                membership = {doc["id"]: cluster_membership(doc, chapters[doc["id"]].text) for doc in cache["documents"]}
                for candidate in pending:
                    left, left_chapter = sources[candidate.left_mention_id]
                    right, right_chapter = sources[candidate.right_mention_id]
                    if left_chapter.id != right_chapter.id:
                        continue
                    groups = membership[str(left_chapter.id)]
                    a = groups.get((left.start_offset, left.end_offset), set())
                    b = groups.get((right.start_offset, right.end_offset), set())
                    if len(a) == len(b) == 1 and a == b:
                        linked[candidate.id] = (left.chapter_id, left.start_offset, left.end_offset, right.start_offset, right.end_offset)
                coreference_metadata = {key: value for key, value in cache.items() if key != "documents"}
            except (ResolutionStopped, ResolutionConflict):
                raise
            except Exception as exc:
                linked.clear()
                coreference_error = "COREFERENCE_TIMEOUT" if isinstance(exc, TimeoutError) else "COREFERENCE_FAILED"
                summary["coreference_fallback"] = coreference_error
                logger.warning("Coreference fallback job=%s code=%s exception_type=%s", job_id, coreference_error, type(exc).__name__)
            # Process shortcuts before spending the limited Gemma call budget.
            pending_ids = deque(sorted(pending_ids, key=lambda key: key not in linked))
            async with SessionLocal() as session, session.begin():
                await current_scope(session, project_id, version_id, lock=True)
                job = await session.get(JobRun, job_id, with_for_update=True)
                require_run(job, attempt)
                _start_stage(job, "entity_resolution", datetime.now(timezone.utc))
                job.error_code = coreference_error
                job.error_message_safe = (
                    "Coreference timed out after 30 minutes; continuing with Gemma. No new coreference merges were applied in this attempt."
                    if coreference_error == "COREFERENCE_TIMEOUT" else
                    "Coreference could not run or returned invalid source spans; continuing with Gemma. No new coreference merges were applied in this attempt."
                    if coreference_error else None
                )

        # Coreference has a separate, cancellable budget; it must not consume the Gemma batch.
        started = time.monotonic()

        timeout = resolution_config().get("request_timeout_seconds", 180)
        calls = 0
        async with httpx.AsyncClient(
            base_url=os.environ["LITELLM_URL"],
            headers={"Authorization": f"Bearer {os.environ['LITELLM_API_KEY']}"},
            timeout=httpx.Timeout(timeout, connect=10),
        ) as client:
            while pending_ids and calls < MAX_CALLS_PER_RUN:
                # The batch budget stops new work; it never truncates a pair's deadline.
                if time.monotonic() - started >= RUN_BUDGET_SECONDS:
                    summary["limit_reached"] = "time_budget"
                    break
                candidate_id = pending_ids.popleft()
                async with SessionLocal() as session:
                    require_run(await session.get(JobRun, job_id), attempt)
                    await current_scope(session, project_id, version_id)
                    candidate = await session.get(ResolutionCandidate, candidate_id)
                    if candidate is None:
                        raise ResolutionConflict("Candidate source changed")
                    if not needs_evaluation(candidate):
                        continue
                    sources = {mention.id: (mention, chapter) for mention, chapter in await source_rows(session, version_id)}
                    pair = make_pair(candidate, sources)
                result = None
                error_code = None
                diagnostics = {"job_id": str(job_id), "run_attempt": attempt, "request_timeout_seconds": timeout,
                               "batch_trace_id": batch_trace_id, "candidate_id": str(candidate_id),
                               "pair_attempt": candidate.model_metadata.get("attempt", 0) + 1,
                               "resolver": "coreference" if candidate_id in linked else "gemma",
                               "pipeline": "coreference_gemma" if combined else "gemma"}
                pair_started = time.monotonic()
                if candidate.error_code:
                    summary["retry_attempts"] += 1
                try:
                    if candidate_id in linked:
                        summary["coreference_shortcuts"] += 1
                        left, chapter = sources[candidate.left_mention_id]
                        right, right_chapter = sources[candidate.right_mention_id]
                        if (right_chapter.id != chapter.id
                                or (chapter.id, left.start_offset, left.end_offset, right.start_offset, right.end_offset) != linked[candidate_id]
                                or hashlib.sha256(chapter.text.encode()).hexdigest() != coreference_hashes[str(chapter.id)]):
                            raise ResolutionConflict("Coreference source changed")
                        # Same exact-span policy as the promoted experiment. Not a confidence score.
                        result = ResolutionResult(
                            ResolutionOutput(decision="merge", evidence_ids=[item["id"] for item in pair.evidence]),
                            COREFERENCE_MODEL, 0, 0, {}, coreference_metadata.get("trace_id"),
                        )
                        diagnostics.update(prompt_version=None, prompt_hash=None, model_alias=None,
                                           configured_model=COREFERENCE_MODEL, model_digest=COREFERENCE_REVISION,
                                           coreference=coreference_metadata)
                    else:
                        calls += 1
                        summary["gemma_attempts"] += 1
                        result = await _resolve_with_stop(pair, client, job_id, attempt, timeout, diagnostics)
                except (EntityResolutionError, json.JSONDecodeError):
                    error_code = "INVALID_MODEL_OUTPUT"
                except (TimeoutError, httpx.TimeoutException):
                    error_code = "MODEL_TIMEOUT"
                except (ConnectionError, httpx.TransportError):
                    error_code = "MODEL_CONNECTION_ERROR"
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    diagnostics["http_status"] = status
                    error_code = ("MODEL_RATE_LIMITED" if status == 429 else
                                  "MODEL_SERVER_ERROR" if status >= 500 else "MODEL_REQUEST_REJECTED")
                diagnostics["latency_ms"] = (time.monotonic() - pair_started) * 1000
                if error_code:
                    summary["failed_attempts"] += 1
                    # Never log provider exception text, credentials, or manuscript excerpts.
                    logger.warning("Resolution pair failed job=%s candidate=%s code=%s elapsed_ms=%.0f trace=%s",
                                   job_id, candidate_id, error_code, diagnostics["latency_ms"], diagnostics.get("trace_id"))
                async with SessionLocal() as session, session.begin():
                    await current_scope(session, project_id, version_id, lock=True)
                    job = await session.get(JobRun, job_id, with_for_update=True)
                    require_run(job, attempt)
                    candidate = await session.get(ResolutionCandidate, candidate_id, with_for_update=True)
                    if candidate is None:
                        raise ResolutionConflict("Candidate source changed")
                    await save_prediction(session, candidate, pair, result, error_code, diagnostics=diagnostics)
                    # The decision and canonical identity commit together, before the next pair.
                    await apply_automatic_predictions(session, version_id)
                    candidates = await candidates_for(session, version_id)
                    job.completed_units = sum(bool(item.llm_decision or item.applied_decision or item.error_code) for item in candidates)
                    committed_totals = trace_counts(candidates)
                # Only committed decisions enter the trace's version totals.
                summary["version_totals"] = committed_totals
                # Provider failures retry in a later job delivery, never in this loop.
                if error_code and needs_evaluation(candidate):
                    retry_pending = True

        async with SessionLocal() as session, session.begin():
            await current_scope(session, project_id, version_id, lock=True)
            job = await session.get(JobRun, job_id, with_for_update=True)
            require_run(job, attempt)
            await apply_automatic_predictions(session, version_id)
            candidates = await candidates_for(session, version_id)
            counts = resolution_counts(candidates)
            committed_totals = trace_counts(candidates)
            now = datetime.now(timezone.utc)
            _finish_stage(job, now)
            job.completed_units = sum(bool(item.llm_decision or item.applied_decision or item.error_code) for item in candidates)
            requeue = counts["remaining"] > 0
            if requeue:
                summary.update(outcome="continuing", end_reason=summary.get("limit_reached", "call_budget" if calls >= MAX_CALLS_PER_RUN else "pending_work"))
                # Keep one job alive across bounded worker slices. Stop can cancel
                # it while queued, and the next task is fenced by its new attempt.
                job.status = "queued"
                _start_stage(job, "queued", now)
                job.completed_at = None
                job.error_code = job.error_message_safe = None
            else:
                summary.update(outcome="completed_with_errors" if counts["error_count"] else "completed",
                               end_reason="no_eligible_pairs")
                job.status = "completed"
                job.stage = "completed_with_errors" if counts["error_count"] else "completed"
                job.completed_at = now
            if not requeue and counts["error_count"]:
                job.error_code = "RESOLUTION_PAIR_ERRORS"
                job.error_message_safe = f"{counts['error_count']} comparisons failed. Other comparisons continued; see each pair's error."
        summary["version_totals"] = committed_totals
        if requeue:
            try:
                if retry_pending:
                    summary["retry_delay_seconds"] = PROVIDER_RETRY_DELAY_SECONDS
                    # ponytail: one short sleep holds a worker slot; add a durable
                    # scheduler only if retry volume makes that operationally costly.
                    await asyncio.sleep(PROVIDER_RETRY_DELAY_SECONDS)
                await resolve_manuscript_entities.kiq(str(job_id))
                summary["continuation_queued"] = True
            except Exception:
                async with SessionLocal() as session, session.begin():
                    job = await session.get(JobRun, job_id, with_for_update=True)
                    # A late dispatch failure must not overwrite Stop or a newer
                    # Resume that is queued but has not incremented attempts yet.
                    if (job is not None and job.status == "queued"
                            and job.attempts == attempt and job.stage_started_at == now):
                        failed_at = datetime.now(timezone.utc)
                        _finish_stage(job, failed_at)
                        job.status = "failed"
                        job.error_code = "QUEUE_UNAVAILABLE"
                        job.error_message_safe = "Could not queue the next batch. Saved decisions are preserved. Resume resolution to continue."
                        job.completed_at = failed_at
                        summary.update(outcome="failed", end_reason="QUEUE_UNAVAILABLE")
                    else:
                        summary.update(outcome="superseded", end_reason="late_queue_failure_discarded")
    except ResolutionStopped as exc:
        summary.update(outcome="stopped" if str(exc) == "user_stopped" else "superseded", end_reason=str(exc))
        return
    except (ResolutionConflict, LookupError):
        summary.update(outcome="failed", end_reason="RESOLUTION_SCOPE_CHANGED")
        await _fail(job_id, "RESOLUTION_SCOPE_CHANGED", attempt)
    except asyncio.CancelledError:
        summary.update(outcome="interrupted", end_reason="worker_cancelled")
        raise
    except Exception as exc:
        summary.update(outcome="failed", end_reason="ENTITY_RESOLUTION_FAILED")
        logger.error("Resolution job failed job=%s exception_type=%s", job_id, type(exc).__name__)
        await _fail(job_id, "ENTITY_RESOLUTION_FAILED", attempt)
    finally:
        summary["duration_ms"] = round((time.monotonic() - batch_started) * 1000)
        annotate_trace(metadata={"outcome": summary["outcome"], "end_reason": summary["end_reason"]},
                       outputs=summary, error_code=summary["end_reason"] if summary["outcome"] == "failed" else None)
        logger.info("Resolution batch job=%s batch=%s trace=%s outcome=%s reason=%s duration_ms=%s",
                    job_id, attempt, batch_trace_id, summary["outcome"], summary["end_reason"], summary["duration_ms"])


@broker.task(retry_on_error=False)
async def resolve_manuscript_entities(job_id: str) -> None:
    await run_resolution_job(uuid.UUID(job_id))
