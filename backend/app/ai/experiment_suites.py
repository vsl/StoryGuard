from dataclasses import dataclass
from typing import Any


CHRISTMAS_CAROL = (
    "A Christmas Carol in Prose; Being a Ghost Story of Christmas"
)
ALICE = "Alice's Adventures in Wonderland"


@dataclass(frozen=True)
class ExperimentSuite:
    id: str
    name: str
    purpose: str
    titles: tuple[str, ...]
    limit: int | None
    shard_count: int


SUITES = {
    suite.id: suite
    for suite in (
        ExperimentSuite(
            id="gacha-smoke",
            name="Gacha smoke · 3 queries",
            purpose="smoke",
            titles=(CHRISTMAS_CAROL,),
            limit=3,
            shard_count=1,
        ),
        ExperimentSuite(
            id="gacha-dev-alice",
            name="Gacha development · Alice · 30 queries",
            purpose="development",
            titles=(ALICE,),
            limit=None,
            shard_count=3,
        ),
        ExperimentSuite(
            id="gacha-dev-christmas",
            name="Gacha development · Christmas Carol · 29 queries",
            purpose="development",
            titles=(CHRISTMAS_CAROL,),
            limit=None,
            shard_count=3,
        ),
        ExperimentSuite(
            id="gacha-dev-all",
            name="Gacha development · both stories · 59 queries",
            purpose="development",
            titles=(CHRISTMAS_CAROL, ALICE),
            limit=None,
            shard_count=6,
        ),
    )
}

CONFIGS = {
    "hybrid-rrf": {
        "id": "hybrid-rrf",
        "name": "Hybrid RRF",
        "retrieval_strategy": "hybrid",
        "reranker": False,
    },
    "hybrid-rrf-reranker": {
        "id": "hybrid-rrf-reranker",
        "name": "Hybrid RRF + cross-encoder",
        "retrieval_strategy": "hybrid",
        "reranker": True,
    },
}


def select_suite_queries(queries: list[dict[str, Any]], suite_id: str) -> list[dict]:
    suite = SUITES.get(suite_id)
    if suite is None:
        raise ValueError("Unknown experiment suite")
    selected = [
        query
        for query in queries
        if query["split"] == "dev" and query["title"] in suite.titles
    ]
    if suite.limit is not None:
        selected = selected[: suite.limit]
    if not selected:
        raise ValueError("Experiment suite has no queries")
    return selected
