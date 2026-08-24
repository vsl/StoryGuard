import asyncio
import hashlib
import json
import os
import statistics
import time
import uuid
from dataclasses import asdict
from pathlib import Path

import httpx

os.environ["STORYGUARD_CHUNK_INDEX"] = "storyguard-chunks-gacha-eval-v2"

from app.ai.retrieval import (
    INDEX_NAME,
    _request,
    replace_version_chunks,
    retrieve_bm25,
)
from app.parsing import (
    ChunkingConfig,
    PARSER_VERSION,
    TOKENIZER_VERSION,
    parse_manuscript,
)


ROOT = Path(__file__).parents[2]
TOP_K = 30
CHUNKING = ChunkingConfig()


async def delete_experiment_index() -> None:
    if INDEX_NAME != "storyguard-chunks-gacha-eval-v2":
        raise RuntimeError("Refusing to delete a non-experiment index")
    try:
        await _request("DELETE", f"/{INDEX_NAME}")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            raise


def load(name: str) -> list[dict]:
    path = ROOT / "data" / "datasets" / "fixtures" / name
    return [json.loads(line) for line in path.read_text().splitlines()]


def fixture_sha256(name: str) -> str:
    return hashlib.sha256(
        (ROOT / "data" / "datasets" / "fixtures" / name).read_bytes()
    ).hexdigest()


def value_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def scope(book_id: str) -> tuple[str, str]:
    return (
        str(uuid.uuid5(uuid.NAMESPACE_URL, f"storyguard:gacha:{book_id}:project")),
        str(uuid.uuid5(uuid.NAMESPACE_URL, f"storyguard:gacha:{book_id}:version")),
    )


def chunk_book(book: dict) -> list[dict[str, object]]:
    project_id, version_id = scope(book["id"])
    parsed = parse_manuscript(
        f"{book['title']}.txt", book["text"].encode(), CHUNKING
    )
    documents = []
    for chapter in parsed.chapters:
        chapter_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"{version_id}:chapter:{chapter.ordinal}")
        )
        for scene in chapter.scenes:
            scene_id = str(
                uuid.uuid5(uuid.NAMESPACE_URL, f"{chapter_id}:scene:{scene.ordinal}")
            )
            for chunk in scene.chunks:
                chunk_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"{scene_id}:{chunk.start_offset}:{chunk.end_offset}:{chunk.content_hash}",
                    )
                )
                documents.append(
                    {
                        "chunk_id": chunk_id,
                        "project_id": project_id,
                        "manuscript_version_id": version_id,
                        "chapter_id": chapter_id,
                        "chapter_ordinal": chapter.ordinal,
                        "scene_id": scene_id,
                        "text": chunk.text,
                        "content_hash": chunk.content_hash,
                    }
                )
    return documents


def metrics(results: list[dict]) -> dict:
    return {
        "query_count": len(results),
        **{
            f"recall_at_{k}": statistics.fmean(
                len(set(row["retrieved_ids"][:k]) & set(row["relevant_ids"]))
                / len(row["relevant_ids"])
                for row in results
            )
            for k in (1, 5, 10, 20)
        },
        "mrr_at_10": statistics.fmean(
            1 / row["rank"] if row["rank"] is not None and row["rank"] <= 10 else 0
            for row in results
        ),
        "median_latency_ms": statistics.median(
            row["latency_ms"] for row in results
        ),
    }


async def run() -> dict:
    books = load("retrieval_documents.jsonl")
    queries = load("retrieval_queries.jsonl")
    documents_by_book = {book["id"]: chunk_book(book) for book in books}
    scopes = {book_id: scope(book_id) for book_id in documents_by_book}
    relevant_by_query = {}
    for query in queries:
        relevant = [
            document["chunk_id"]
            for document in documents_by_book[query["book_id"]]
            if query["evidence"] in document["text"]
        ]
        if not relevant:
            raise ValueError(f"No StoryGuard chunk contains evidence for {query['id']}")
        relevant_by_query[query["id"]] = relevant

    results = []
    await delete_experiment_index()
    try:
        for book_id, documents in documents_by_book.items():
            project_id, version_id = scopes[book_id]
            await replace_version_chunks(project_id, version_id, documents)

        for query in queries:
            project_id, version_id = scopes[query["book_id"]]
            started = time.perf_counter()
            hits = await retrieve_bm25(
                query["query"], project_id, version_id, top_k=TOP_K
            )
            latency_ms = (time.perf_counter() - started) * 1_000
            if any(
                hit.project_id != project_id
                or hit.manuscript_version_id != version_id
                for hit in hits
            ):
                raise RuntimeError("Retrieval returned a chunk outside the book scope")
            retrieved_ids = [hit.chunk_id for hit in hits]
            relevant_ids = relevant_by_query[query["id"]]
            relevant_ranks = [
                retrieved_ids.index(chunk_id) + 1
                for chunk_id in relevant_ids
                if chunk_id in retrieved_ids
            ]
            results.append(
                {
                    "book": query["title"],
                    "id": query["id"],
                    "latency_ms": latency_ms,
                    "query": query["query"],
                    "rank": min(relevant_ranks) if relevant_ranks else None,
                    "relevant_ids": relevant_ids,
                    "retrieved_ids": retrieved_ids,
                    "split": query["split"],
                }
            )
    finally:
        await delete_experiment_index()

    failures = [row for row in results if row["rank"] != 1]
    return {
        "strategy": "bm25",
        "dataset": {
            "id": "feyninc/gacha",
            "revision": "076b8b186236941df371a8d9b14be4cb4c7498fb",
            "corpus_config": "corpus",
            "question_config": "questions",
            "split": "train",
            "book_count": len(books),
            "chunk_count": sum(map(len, documents_by_book.values())),
            "qrel_count": sum(map(len, relevant_by_query.values())),
            "parser_version": PARSER_VERSION,
            "tokenizer_version": TOKENIZER_VERSION,
            "chunking": asdict(CHUNKING),
            "queries_sha256": fixture_sha256("retrieval_queries.jsonl"),
            "documents_sha256": fixture_sha256("retrieval_documents.jsonl"),
            "chunks_sha256": value_sha256(documents_by_book),
            "qrels_sha256": value_sha256(relevant_by_query),
            "ground_truth": "all same-book StoryGuard chunks containing exact evidence",
        },
        "candidate_top_k": TOP_K,
        "splits": {
            split: metrics([row for row in results if row["split"] == split])
            for split in ("dev", "test")
        },
        "all": metrics(results),
        "multiple_relevant_query_count": sum(
            len(row["relevant_ids"]) > 1 for row in results
        ),
        "non_rank_1_query_count": len(failures),
        "non_rank_1_examples": [
            {
                "book": row["book"],
                "query": row["query"],
                "first_relevant_rank": row["rank"],
                "relevant_count": len(row["relevant_ids"]),
            }
            for row in failures[:20]
        ],
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), indent=2))
