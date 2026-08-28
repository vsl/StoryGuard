import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.ai.experiment_suites import SUITES
from app.db.models.experiment_run import ExperimentRun
from app.db.session import SessionLocal
from app.queue.broker import broker


LOGGER = logging.getLogger(__name__)
BACKEND_ROOT = Path(__file__).parents[3]
SCRIPT = BACKEND_ROOT / "scripts" / "bm25_experiment.py"
OUTPUT_ROOT = Path(
    os.environ.get("STORYGUARD_LOCAL_DIR", BACKEND_ROOT.parent / ".local")
) / "experiments" / "lab"
PHASE_TIMEOUT_SECONDS = int(os.environ.get("EXPERIMENT_PHASE_TIMEOUT_SECONDS", "7200"))


async def _run_phase(*arguments: str) -> dict:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(SCRIPT),
        "--output-dir",
        str(OUTPUT_ROOT),
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=PHASE_TIMEOUT_SECONDS
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError("Experiment phase timed out")
    if process.returncode:
        LOGGER.error(
            "Experiment subprocess failed",
            extra={
                "returncode": process.returncode,
                "stderr": stderr.decode(errors="replace")[-2000:],
            },
        )
        raise RuntimeError("Experiment phase failed")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Experiment phase returned invalid output") from exc


def _tracing_enabled() -> bool:
    return os.environ.get("LANGSMITH_TRACING", "false").lower() == "true"


async def _traced_phase(
    experiment_id: uuid.UUID,
    label: str,
    trace_ids: dict[str, str],
    *arguments: str,
) -> dict:
    if not _tracing_enabled():
        return await _run_phase(*arguments)
    trace_id = str(uuid.uuid5(experiment_id, label))
    result = await _run_phase(
        *arguments,
        "--experiment-run-id",
        str(experiment_id),
        "--trace-id",
        trace_id,
    )
    trace_ids[label] = trace_id
    return result


async def _progress(
    run_id: uuid.UUID, *, status: str, stage: str, completed: int
) -> None:
    async with SessionLocal() as session, session.begin():
        run = await session.get(ExperimentRun, run_id, with_for_update=True)
        if run is None or run.status in {"completed", "failed"}:
            return
        run.status = status
        run.stage = stage
        run.completed_units = completed


def _metric_pairs(aggregate: dict) -> dict:
    baseline = aggregate["strategies"]["hybrid"]
    candidate = aggregate["strategies"]["hybrid_reranker"]
    return {
        name: {"baseline": baseline[name], "candidate": candidate[name]}
        for name in (
            "recall_at_10",
            "mrr_at_10",
            "p50_latency_ms",
            "p95_latency_ms",
        )
    } | {"api_cost_usd": {"baseline": 0.0, "candidate": 0.0}}


def _failures(
    aggregate: dict,
    query_ids: list[str],
    shard_count: int,
    trace_ids: dict[str, str],
) -> list[dict]:
    failures = []
    for row in aggregate.get("regression_examples", []):
        shard_index = query_ids.index(row["id"]) % shard_count
        failures.append(
            {
                "id": row["id"],
                "type": "reranker_regression",
                "question": row["query"],
                "summary": "The reranker moved relevant evidence lower.",
                "baseline_output": f"First relevant rank: {row['baseline_rank']}",
                "candidate_output": f"First relevant rank: {row['reranker_rank']}",
                "trace_id": trace_ids.get(f"rerank:{shard_index}"),
            }
        )
    for row in aggregate.get("candidate_pool_miss_examples", []):
        shard_index = query_ids.index(row["id"]) % shard_count
        failures.append(
            {
                "id": row["id"],
                "type": "candidate_pool_miss",
                "question": row["query"],
                "summary": "Hybrid retrieval did not include relevant evidence in Top-30.",
                "baseline_output": "Relevant evidence absent from Top-30",
                "candidate_output": "Reranker cannot recover absent evidence",
                "trace_id": trace_ids.get(f"candidates:{shard_index}"),
            }
        )
    return failures


async def _complete(
    run_id: uuid.UUID, aggregate: dict, trace_ids: dict[str, str]
) -> None:
    async with SessionLocal() as session, session.begin():
        run = await session.get(ExperimentRun, run_id, with_for_update=True)
        if run is None or run.status == "completed":
            return
        run.status = "completed"
        run.stage = "completed"
        run.completed_units = run.total_units
        run.active_slot = None
        run.metrics = _metric_pairs(aggregate)
        query_ids = run.config_snapshot["dataset"]["query_ids"]
        shard_count = run.config_snapshot["shard_count"]
        run.failures = _failures(aggregate, query_ids, shard_count, trace_ids)
        run.observability = {
            "langsmith_enabled": _tracing_enabled(),
            "trace_ids": list(trace_ids.values()),
            "candidate_fingerprint": aggregate["candidate_fingerprint"],
            "reranker_fingerprint": aggregate["reranker_fingerprint"],
        }
        run.completed_at = datetime.now(timezone.utc)


async def _fail(run_id: uuid.UUID) -> None:
    async with SessionLocal() as session, session.begin():
        run = await session.get(ExperimentRun, run_id, with_for_update=True)
        if run is None or run.status == "completed":
            return
        run.status = "failed"
        run.stage = "failed"
        run.active_slot = None
        run.error_code = "EXPERIMENT_FAILED"
        run.error_message_safe = "The experiment could not be completed."
        run.completed_at = datetime.now(timezone.utc)


async def run_experiment_job(experiment_id: uuid.UUID) -> None:
    async with SessionLocal() as session, session.begin():
        run = await session.scalar(
            select(ExperimentRun)
            .where(ExperimentRun.id == experiment_id)
            .with_for_update()
        )
        if run is None:
            raise LookupError("Experiment not found")
        if run.status in {"completed", "failed"}:
            return
        run.status = "running"
        run.stage = "preparing_index"
        run.attempts += 1
        run.started_at = run.started_at or datetime.now(timezone.utc)
        suite_id = run.dataset_id
        shard_count = SUITES[suite_id].shard_count

    completed = 0
    trace_ids: dict[str, str] = {}
    try:
        await _traced_phase(
            experiment_id,
            "prepare",
            trace_ids,
            "--phase",
            "prepare",
            "--suite",
            suite_id,
        )
        completed += 1
        await _progress(
            experiment_id,
            status="running",
            stage="retrieving_candidates",
            completed=completed,
        )
        for shard_index in range(shard_count):
            await _traced_phase(
                experiment_id,
                f"candidates:{shard_index}",
                trace_ids,
                "--phase",
                "candidates",
                "--suite",
                suite_id,
                "--shard-index",
                str(shard_index),
                "--shard-count",
                str(shard_count),
            )
            completed += 1
            await _progress(
                experiment_id,
                status="running",
                stage=f"candidates_{shard_index + 1}_of_{shard_count}",
                completed=completed,
            )
        for shard_index in range(shard_count):
            await _traced_phase(
                experiment_id,
                f"rerank:{shard_index}",
                trace_ids,
                "--phase", "rerank", "--shard-index", str(shard_index)
            )
            completed += 1
            await _progress(
                experiment_id,
                status="running",
                stage=f"reranking_{shard_index + 1}_of_{shard_count}",
                completed=completed,
            )
        await _progress(
            experiment_id,
            status="scoring",
            stage="aggregating_metrics",
            completed=completed,
        )
        result = await _traced_phase(
            experiment_id,
            "aggregate",
            trace_ids,
            "--phase",
            "aggregate",
        )
        aggregate_path = Path(result["path"]).resolve()
        if not aggregate_path.is_relative_to(OUTPUT_ROOT.resolve()):
            raise RuntimeError("Experiment aggregate path is outside artifact storage")
        aggregate = json.loads(aggregate_path.read_text())
        await _complete(experiment_id, aggregate, trace_ids)
    except Exception:
        LOGGER.exception(
            "Experiment run failed", extra={"experiment_id": str(experiment_id)}
        )
        await _fail(experiment_id)
        raise


@broker.task
async def run_experiment(run_id: str) -> None:
    await run_experiment_job(uuid.UUID(run_id))
