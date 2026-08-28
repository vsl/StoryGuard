import os
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.experiment_suites import CONFIGS, SUITES
from app.ai.experiments import dataset_catalog, experiment_snapshot
from app.db.models.experiment_run import ExperimentRun
from app.db.session import get_session
from app.queue.tasks.experiments import run_experiment
from app.schemas.experiments import (
    ExperimentConfigRead,
    ExperimentCreate,
    ExperimentDatasetRead,
    ExperimentFailureRead,
    ExperimentRead,
)


router = APIRouter(prefix="/api/developer", tags=["developer"])
Session = Annotated[AsyncSession, Depends(get_session)]


def _read(run: ExperimentRun) -> ExperimentRead:
    snapshot = run.config_snapshot
    return ExperimentRead(
        id=run.id,
        status=run.status,
        stage=run.stage,
        dataset=snapshot["dataset"]["name"],
        baseline=snapshot["baseline"]["name"],
        candidate=snapshot["candidate"]["name"],
        completed=run.completed_units,
        total=run.total_units,
        metrics=run.metrics,
        error_code=run.error_code,
        error_message_safe=run.error_message_safe,
        observability=run.observability,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


async def _run_or_404(run_id: uuid.UUID, session: AsyncSession) -> ExperimentRun:
    run = await session.get(ExperimentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return run


@router.get("/datasets", response_model=list[ExperimentDatasetRead])
async def list_datasets() -> list[dict]:
    return dataset_catalog()


@router.get("/experiment-configs", response_model=list[ExperimentConfigRead])
async def list_experiment_configs() -> list[dict]:
    return list(CONFIGS.values())


@router.post(
    "/experiments",
    response_model=ExperimentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_experiment(
    payload: ExperimentCreate, session: Session
) -> ExperimentRead | JSONResponse:
    try:
        snapshot = experiment_snapshot(
            payload.dataset_id,
            payload.baseline_config_id,
            payload.candidate_config_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    shard_count = SUITES[payload.dataset_id].shard_count
    run = ExperimentRun(
        dataset_id=payload.dataset_id,
        baseline_config_id=payload.baseline_config_id,
        candidate_config_id=payload.candidate_config_id,
        stage="queued",
        completed_units=0,
        total_units=2 + 2 * shard_count,
        active_slot=1,
        config_snapshot=snapshot,
        observability={
            "langsmith_enabled": os.environ.get("LANGSMITH_TRACING", "false").lower()
            == "true",
            "trace_ids": [],
        },
    )
    session.add(run)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="Another experiment is already active"
        ) from exc
    await session.refresh(run)

    try:
        await run_experiment.kiq(str(run.id))
    except Exception:
        run.status = "failed"
        run.stage = "queue_failed"
        run.active_slot = None
        run.error_code = "QUEUE_UNAVAILABLE"
        run.error_message_safe = "The experiment could not be queued."
        await session.commit()
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": run.error_code,
                    "message": run.error_message_safe,
                }
            },
        )
    return _read(run)


@router.get("/experiments", response_model=list[ExperimentRead])
async def list_experiments(session: Session) -> list[ExperimentRead]:
    runs = await session.scalars(
        select(ExperimentRun).order_by(
            ExperimentRun.created_at.desc(), ExperimentRun.id.desc()
        ).limit(50)
    )
    return [_read(run) for run in runs]


@router.get("/experiments/{run_id}", response_model=ExperimentRead)
async def get_experiment(run_id: uuid.UUID, session: Session) -> ExperimentRead:
    return _read(await _run_or_404(run_id, session))


@router.get(
    "/experiments/{run_id}/failures",
    response_model=list[ExperimentFailureRead],
)
async def list_experiment_failures(
    run_id: uuid.UUID, session: Session
) -> list[dict]:
    run = await _run_or_404(run_id, session)
    return run.failures or []
