import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.ai.experiments import dataset_catalog, experiment_snapshot


class ExperimentCatalogTest(unittest.TestCase):
    def test_catalog_has_only_diagnostic_development_suites(self) -> None:
        catalog = {item["id"]: item for item in dataset_catalog()}

        self.assertEqual(catalog["gacha-smoke"]["query_count"], 3)
        self.assertEqual(catalog["gacha-dev-alice"]["query_count"], 30)
        self.assertEqual(catalog["gacha-dev-christmas"]["query_count"], 29)
        self.assertEqual(catalog["gacha-dev-all"]["query_count"], 59)
        self.assertFalse(any(item["promotion_eligible"] for item in catalog.values()))

    def test_snapshot_accepts_only_the_controlled_pair(self) -> None:
        snapshot = experiment_snapshot(
            "gacha-smoke", "hybrid-rrf", "hybrid-rrf-reranker"
        )
        self.assertEqual(len(snapshot["dataset"]["query_ids"]), 3)
        self.assertEqual(snapshot["shard_count"], 1)
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            experiment_snapshot(
                "gacha-smoke", "hybrid-rrf-reranker", "hybrid-rrf"
            )


RUN_DATABASE_TESTS = os.environ.get("RUN_DATABASE_TESTS") == "1"

if RUN_DATABASE_TESTS:
    import httpx
    from sqlalchemy import select

    from app.db.models.experiment_run import ExperimentRun
    from app.db.session import SessionLocal, engine
    from app.main import app
    from app.queue.tasks.experiments import run_experiment_job


@unittest.skipUnless(RUN_DATABASE_TESTS, "set RUN_DATABASE_TESTS=1")
class ExperimentIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.run_ids: set[uuid.UUID] = set()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )

    async def asyncTearDown(self) -> None:
        async with SessionLocal() as session, session.begin():
            for run_id in self.run_ids:
                run = await session.get(ExperimentRun, run_id)
                if run is not None:
                    await session.delete(run)
        await self.client.aclose()
        await engine.dispose()

    async def _create(self) -> dict:
        with patch(
            "app.api.experiments.run_experiment.kiq", new=AsyncMock()
        ):
            response = await self.client.post(
                "/api/developer/experiments",
                json={
                    "dataset_id": "gacha-smoke",
                    "baseline_config_id": "hybrid-rrf",
                    "candidate_config_id": "hybrid-rrf-reranker",
                },
            )
        self.assertEqual(response.status_code, 201)
        result = response.json()
        self.run_ids.add(uuid.UUID(result["id"]))
        return result

    async def test_api_persists_snapshot_and_rejects_concurrent_run(self) -> None:
        datasets = await self.client.get("/api/developer/datasets")
        self.assertEqual(datasets.status_code, 200)
        self.assertEqual(datasets.json()[0]["query_count"], 3)

        created = await self._create()
        self.assertEqual((created["status"], created["total"]), ("queued", 4))
        with patch(
            "app.api.experiments.run_experiment.kiq", new=AsyncMock()
        ):
            duplicate = await self.client.post(
                "/api/developer/experiments",
                json={
                    "dataset_id": "gacha-smoke",
                    "baseline_config_id": "hybrid-rrf",
                    "candidate_config_id": "hybrid-rrf-reranker",
                },
            )
        self.assertEqual(duplicate.status_code, 409)

        detail = await self.client.get(
            f"/api/developer/experiments/{created['id']}"
        )
        self.assertEqual(detail.json()["dataset"], "Gacha smoke · 3 queries")

    async def test_queue_failure_is_safe(self) -> None:
        with patch(
            "app.api.experiments.run_experiment.kiq",
            new=AsyncMock(side_effect=RuntimeError("amqp://secret")),
        ):
            response = await self.client.post(
                "/api/developer/experiments",
                json={
                    "dataset_id": "gacha-smoke",
                    "baseline_config_id": "hybrid-rrf",
                    "candidate_config_id": "hybrid-rrf-reranker",
                },
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "QUEUE_UNAVAILABLE")
        self.assertNotIn("secret", response.text)
        async with SessionLocal() as session:
            run = await session.scalar(
                select(ExperimentRun).order_by(ExperimentRun.created_at.desc())
            )
        self.run_ids.add(run.id)

    async def test_worker_runs_phases_and_duplicate_delivery_is_a_no_op(self) -> None:
        created = await self._create()
        run_id = uuid.UUID(created["id"])
        aggregate = {
            "candidate_fingerprint": "a" * 64,
            "reranker_fingerprint": "b" * 64,
            "strategies": {
                "hybrid": {
                    "recall_at_10": 0.8,
                    "mrr_at_10": 0.7,
                    "p50_latency_ms": 10.0,
                    "p95_latency_ms": 12.0,
                },
                "hybrid_reranker": {
                    "recall_at_10": 1.0,
                    "mrr_at_10": 0.9,
                    "p50_latency_ms": 100.0,
                    "p95_latency_ms": 120.0,
                },
            },
            "regression_examples": [],
            "candidate_pool_miss_examples": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            aggregate_path = Path(directory) / "aggregate.json"
            aggregate_path.write_text(json.dumps(aggregate))
            phase = AsyncMock(
                side_effect=[
                    {"status": "complete"},
                    {"status": "complete"},
                    {"status": "complete"},
                    {"status": "complete", "path": str(aggregate_path)},
                ]
            )
            with (
                patch("app.queue.tasks.experiments.OUTPUT_ROOT", Path(directory)),
                patch("app.queue.tasks.experiments._run_phase", phase),
            ):
                await run_experiment_job(run_id)
                await run_experiment_job(run_id)

        async with SessionLocal() as session:
            run = await session.get(ExperimentRun, run_id)
        self.assertEqual((run.status, run.attempts), ("completed", 1))
        self.assertEqual((run.completed_units, run.total_units), (4, 4))
        self.assertEqual(run.metrics["recall_at_10"]["candidate"], 1.0)


if __name__ == "__main__":
    unittest.main()
