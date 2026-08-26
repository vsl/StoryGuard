import argparse
import asyncio
import gc
import hashlib
import json
import statistics
import time
import uuid
from dataclasses import asdict
from importlib.metadata import version as package_version
from pathlib import Path

import httpx

from app.ai import retrieval
from app.ai.embeddings import (
    EMBEDDING_DIMENSION,
    EMBEDDING_REPOSITORY,
    EMBEDDING_REVISION,
    EMBEDDING_VERSION,
    embed_documents,
    get_embedding_provider,
)
from app.ai.retrieval import (
    RRF_RANK_CONSTANT,
    RRF_RANK_WINDOW,
    _request,
    replace_version_chunks,
    retrieve_bm25,
    retrieve_hybrid,
    retrieve_vector,
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
# ponytail: immutable indexes accumulate; add retention when disk usage matters.
EXPERIMENT_INDEX_PREFIX = "storyguard-chunks-gacha-eval-"


async def delete_experiment_index() -> None:
    fingerprint = retrieval.INDEX_NAME.removeprefix(EXPERIMENT_INDEX_PREFIX)
    if len(fingerprint) != 64 or any(
        character not in "0123456789abcdef" for character in fingerprint
    ):
        raise RuntimeError("Refusing to delete a non-experiment index")
    try:
        await _request("DELETE", f"/{retrieval.INDEX_NAME}")
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


def experiment_fingerprint(
    chunks_sha256: str,
    elasticsearch_version: str,
    include_embeddings: bool,
) -> str:
    return value_sha256(
        {
            "chunks_sha256": chunks_sha256,
            "parser_version": PARSER_VERSION,
            "tokenizer_version": TOKENIZER_VERSION,
            "chunking": asdict(CHUNKING),
            "elasticsearch_version": elasticsearch_version,
            "index_mapping": retrieval.INDEX_MAPPING,
            "mode": "vector" if include_embeddings else "lexical",
            "embedding": {
                "repository": EMBEDDING_REPOSITORY,
                "revision": EMBEDDING_REVISION,
                "version": EMBEDDING_VERSION,
                "dimension": EMBEDDING_DIMENSION,
                "document_encoder": "encode_document",
                "normalize_embeddings": True,
                "sentence_transformers": package_version(
                    "sentence-transformers"
                ),
                "torch": package_version("torch"),
            }
            if include_embeddings
            else None,
        }
    )


async def experiment_index_complete(
    expected_count: int, require_embeddings: bool
) -> bool:
    try:
        response = await _request("GET", f"/{retrieval.INDEX_NAME}/_count")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return False
        raise
    if response.json()["count"] != expected_count:
        return False
    if not require_embeddings:
        return True
    response = await _request(
        "POST",
        f"/{retrieval.INDEX_NAME}/_count",
        json={"query": {"term": {"embedding_version": EMBEDDING_VERSION}}},
    )
    return response.json()["count"] == expected_count


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


async def evaluate(
    strategy: str,
    queries: list[dict],
    scopes: dict[str, tuple[str, str]],
    relevant_by_query: dict[str, list[str]],
) -> list[dict]:
    retrieve = {
        "bm25": retrieve_bm25,
        "vector": retrieve_vector,
        "hybrid": retrieve_hybrid,
    }[strategy]
    results = []
    for query in queries:
        project_id, version_id = scopes[query["book_id"]]
        started = time.perf_counter()
        hits = await retrieve(query["query"], project_id, version_id, top_k=TOP_K)
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
        rank = min(relevant_ranks) if relevant_ranks else None
        results.append(
            {
                "answer": query["answer"],
                "book": query["title"],
                "evidence": query["evidence"],
                "id": query["id"],
                "latency_ms": latency_ms,
                "query": query["query"],
                "rank": rank,
                "relevant_ids": relevant_ids,
                "retrieved_ids": retrieved_ids,
                "split": query["split"],
                "top_chunks": [
                    {
                        "contains_exact_evidence": query["evidence"] in hit.text,
                        "preview": " ".join(hit.text.split())[:600],
                        "rank": hit_rank,
                        "score": hit.score,
                    }
                    for hit_rank, hit in enumerate(hits[:10], 1)
                ]
                if rank is None or rank > 10
                else [],
            }
        )
    return results


def report(
    strategy: str,
    results: list[dict],
    dataset: dict,
) -> dict:
    failures = [row for row in results if row["rank"] != 1]
    hard_test_failures = [
        row
        for row in results
        if row["split"] == "test" and (row["rank"] is None or row["rank"] > 10)
    ]
    return {
        "strategy": strategy,
        "dataset": dataset,
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
        "diagnostic_examples": [
            {
                "book": row["book"],
                "question": row["query"],
                "gold_answer": row["answer"],
                "gold_evidence": row["evidence"],
                "first_labeled_rank": row["rank"],
                "top_10_chunks": row["top_chunks"],
            }
            for row in hard_test_failures[:3]
        ],
    }


async def run(strategy: str = "bm25") -> dict:
    if strategy not in {"bm25", "vector", "hybrid", "compare"}:
        raise ValueError("strategy must be bm25, vector, hybrid, or compare")
    books = load("retrieval_documents.jsonl")
    queries = load("retrieval_queries.jsonl")
    documents_by_book = {book["id"]: chunk_book(book) for book in books}
    all_documents = [
        document
        for book_documents in documents_by_book.values()
        for document in book_documents
    ]
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

    dataset = {
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
    }
    require_embeddings = strategy in {"vector", "hybrid", "compare"}
    elasticsearch = await _request("GET", "/")
    elasticsearch_version = str(elasticsearch.json()["version"]["number"])
    fingerprint = experiment_fingerprint(
        str(dataset["chunks_sha256"]), elasticsearch_version, require_embeddings
    )
    retrieval.INDEX_NAME = EXPERIMENT_INDEX_PREFIX + fingerprint
    cache_hit = await experiment_index_complete(
        len(all_documents), require_embeddings
    )

    model_load_ms = document_embedding_ms = documents_per_second = None
    index_build_ms = None
    if not cache_hit:
        await delete_experiment_index()
    if require_embeddings and not cache_hit:
        started = time.perf_counter()
        await asyncio.to_thread(get_embedding_provider)
        model_load_ms = (time.perf_counter() - started) * 1_000
        started = time.perf_counter()
        vectors = await asyncio.to_thread(
            embed_documents,
            [str(document["text"]) for document in all_documents],
        )
        document_embedding_ms = (time.perf_counter() - started) * 1_000
        for document, vector in zip(all_documents, vectors, strict=True):
            document["embedding_version"] = EMBEDDING_VERSION
            document["embedding"] = vector
        documents_per_second = len(all_documents) / (
            document_embedding_ms / 1_000
        )

    if not cache_hit:
        started = time.perf_counter()
        for book_id, book_documents in documents_by_book.items():
            project_id, version_id = scopes[book_id]
            await replace_version_chunks(project_id, version_id, book_documents)
        index_build_ms = (time.perf_counter() - started) * 1_000
        if not await experiment_index_complete(
            len(all_documents), require_embeddings
        ):
            raise RuntimeError("Experiment index is incomplete after build")

    cache_stats = {
        "document_cache_hit": cache_hit,
        "experiment_index": retrieval.INDEX_NAME,
        "fingerprint": fingerprint,
        "elasticsearch_version": elasticsearch_version,
        "document_embedding_ms": document_embedding_ms,
        "index_build_ms": index_build_ms,
    }
    embedding_stats = {
        "provider": "sentence_transformers",
        "version": EMBEDDING_VERSION,
        "model_load_ms": model_load_ms,
        "documents_per_second": documents_per_second,
    }

    if require_embeddings:
        get_embedding_provider.cache_clear()
        gc.collect()
    results_by_strategy = {}
    if strategy in {"bm25", "compare"}:
        results_by_strategy["bm25"] = await evaluate(
            "bm25", queries, scopes, relevant_by_query
        )
    if strategy in {"vector", "compare"}:
        results_by_strategy["vector"] = await evaluate(
            "vector", queries, scopes, relevant_by_query
        )
    if strategy in {"hybrid", "compare"}:
        results_by_strategy["hybrid"] = await evaluate(
            "hybrid", queries, scopes, relevant_by_query
        )

    reports = {
        name: report(name, results, dataset)
        for name, results in results_by_strategy.items()
    }
    for strategy_report in reports.values():
        strategy_report["document_cache"] = cache_stats
    if "vector" in reports:
        vector_results = results_by_strategy["vector"]
        reports["vector"]["embedding"] = embedding_stats
        reports["vector"]["cold_query_latency_ms"] = vector_results[0]["latency_ms"]
        reports["vector"]["warm_median_latency_ms"] = statistics.median(
            row["latency_ms"] for row in vector_results[1:]
        )
    if "hybrid" in reports:
        reports["hybrid"]["rrf"] = {
            "rank_constant": RRF_RANK_CONSTANT,
            "rank_window": RRF_RANK_WINDOW,
        }
        reports["hybrid"]["embedding"] = embedding_stats
    if strategy != "compare":
        return reports[strategy]

    results = [
        {
            "book": bm25["book"],
            "query": bm25["query"],
            "bm25_rank": bm25["rank"],
            "vector_rank": vector["rank"],
            "hybrid_rank": hybrid["rank"],
        }
        for bm25, vector, hybrid in zip(
            results_by_strategy["bm25"],
            results_by_strategy["vector"],
            results_by_strategy["hybrid"],
            strict=True,
        )
    ]
    summaries = {
        name: {
            "strategy": strategy_report["strategy"],
            "splits": strategy_report["splits"],
            "all": strategy_report["all"],
            "non_rank_1_query_count": strategy_report["non_rank_1_query_count"],
            **(
                {
                    "cold_query_latency_ms": strategy_report[
                        "cold_query_latency_ms"
                    ],
                    "warm_median_latency_ms": strategy_report[
                        "warm_median_latency_ms"
                    ],
                }
                if name == "vector"
                else {}
            ),
        }
        for name, strategy_report in reports.items()
    }
    improvements = [
        row
        for row in results
        if (row["hybrid_rank"] or TOP_K + 1) < (row["bm25_rank"] or TOP_K + 1)
    ]
    regressions = [
        row
        for row in results
        if (row["hybrid_rank"] or TOP_K + 1) > (row["bm25_rank"] or TOP_K + 1)
    ]
    return {
        "dataset": dataset,
        "document_cache": cache_stats,
        "embedding": embedding_stats,
        "rrf": reports["hybrid"]["rrf"],
        "strategies": summaries,
        "hybrid_rank_change_count": sum(
            row["bm25_rank"] != row["hybrid_rank"] for row in results
        ),
        "hybrid_improvement_count": len(improvements),
        "hybrid_improvement_examples": improvements[:10],
        "hybrid_regression_count": len(regressions),
        "hybrid_regression_examples": regressions[:10],
        "anne_diagnostic": next(
            row for row in results if "correct spelling" in row["query"]
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strategy",
        choices=("bm25", "vector", "hybrid", "compare"),
        default="bm25",
    )
    print(json.dumps(asyncio.run(run(parser.parse_args().strategy)), indent=2))
