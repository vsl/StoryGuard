import asyncio
import hashlib
import json
import statistics
import time
import uuid
from pathlib import Path

from app.ai.retrieval import replace_version_chunks, retrieve_bm25


ROOT = Path(__file__).parents[2]
PROJECT_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "storyguard:bm25-eval-project"))
VERSION_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "storyguard:bm25-eval-version"))


def load(name: str) -> list[dict]:
    path = ROOT / "data" / "datasets" / "fixtures" / name
    return [json.loads(line) for line in path.read_text().splitlines()]


async def run() -> dict:
    source_documents = load("retrieval_documents.jsonl")
    queries = load("retrieval_queries.jsonl")
    documents = [
        {
            "chunk_id": row["id"],
            "project_id": PROJECT_ID,
            "manuscript_version_id": VERSION_ID,
            "chapter_id": row["id"].split("_")[0],
            "chapter_ordinal": index,
            "scene_id": None,
            "text": row["text"],
            "content_hash": hashlib.sha256(row["text"].encode()).hexdigest(),
        }
        for index, row in enumerate(source_documents, 1)
    ]
    await replace_version_chunks(PROJECT_ID, VERSION_ID, documents)
    ranks, latencies, failures = [], [], []
    try:
        for row in queries:
            started = time.perf_counter()
            hits = await retrieve_bm25(
                row["query"], PROJECT_ID, VERSION_ID, top_k=30
            )
            latencies.append((time.perf_counter() - started) * 1_000)
            ids = [hit.chunk_id for hit in hits]
            rank = ids.index(row["relevant_chunk_id"]) + 1 if row["relevant_chunk_id"] in ids else None
            ranks.append(rank)
            if rank != 1:
                failures.append(
                    {
                        "query": row["query"],
                        "relevant_chunk_id": row["relevant_chunk_id"],
                        "rank": rank,
                    }
                )
    finally:
        await replace_version_chunks(PROJECT_ID, VERSION_ID, [])

    return {
        "strategy": "bm25",
        "query_count": len(queries),
        "candidate_count": len(documents),
        **{
            f"recall_at_{k}": sum(rank is not None and rank <= k for rank in ranks)
            / len(ranks)
            for k in (1, 5, 10, 30)
        },
        "mrr": sum(1 / rank if rank else 0 for rank in ranks) / len(ranks),
        "median_latency_ms": statistics.median(latencies),
        "non_rank_1_queries": failures,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), indent=2))
