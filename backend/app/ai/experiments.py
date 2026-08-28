import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

import yaml

from app.ai.experiment_suites import CONFIGS, SUITES, select_suite_queries


ROOT = Path(__file__).parents[3]
DATA_DIR = Path(os.environ.get("STORYGUARD_DATA_DIR", ROOT / "data"))
DATASETS_CONFIG = Path(
    os.environ.get("STORYGUARD_DATASETS_CONFIG", ROOT / "config" / "datasets.yaml")
)


@lru_cache(maxsize=1)
def _queries() -> list[dict]:
    path = DATA_DIR / "datasets" / "fixtures" / "retrieval_queries.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


@lru_cache(maxsize=1)
def _retrieval_registry() -> dict:
    registry = yaml.safe_load(DATASETS_CONFIG.read_text())
    return registry["datasets"]["retrieval_eval"]


def _manifest_sha256(query_ids: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(query_ids, separators=(",", ":")).encode()
    ).hexdigest()


def dataset_catalog() -> list[dict]:
    revision = _retrieval_registry()["revision"]
    result = []
    for suite in SUITES.values():
        queries = select_suite_queries(_queries(), suite.id)
        result.append(
            {
                "id": suite.id,
                "name": suite.name,
                "purpose": suite.purpose,
                "stories": list(suite.titles),
                "query_count": len(queries),
                "revision": revision,
                "manifest_sha256": _manifest_sha256(
                    [query["id"] for query in queries]
                ),
                "promotion_eligible": False,
            }
        )
    return result


def experiment_snapshot(
    dataset_id: str, baseline_config_id: str, candidate_config_id: str
) -> dict:
    if dataset_id not in SUITES:
        raise ValueError("Unknown dataset configuration")
    if (
        baseline_config_id != "hybrid-rrf"
        or candidate_config_id != "hybrid-rrf-reranker"
    ):
        raise ValueError("Unsupported experiment configuration pair")
    dataset = next(item for item in dataset_catalog() if item["id"] == dataset_id)
    query_ids = [
        query["id"] for query in select_suite_queries(_queries(), dataset_id)
    ]
    return {
        "dataset": {**dataset, "query_ids": query_ids},
        "baseline": CONFIGS[baseline_config_id],
        "candidate": CONFIGS[candidate_config_id],
        "shard_count": SUITES[dataset_id].shard_count,
    }
