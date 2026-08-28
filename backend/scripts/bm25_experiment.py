import argparse
import asyncio
import gc
import hashlib
import json
import math
import os
import statistics
import time
import uuid
from dataclasses import asdict
from importlib.metadata import version as package_version
from pathlib import Path

import httpx
from langsmith import trace

from app.ai import retrieval
from app.ai.experiment_suites import SUITES, select_suite_queries
from app.ai.embeddings import (
    EMBEDDING_DIMENSION,
    EMBEDDING_REPOSITORY,
    EMBEDDING_REVISION,
    EMBEDDING_VERSION,
    embed_documents,
    get_embedding_provider,
)
from app.ai.reranking import (
    RERANKER_BATCH_SIZE,
    RERANKER_REPOSITORY,
    RERANKER_REVISION,
    RERANKER_VERSION,
    get_reranker,
    rerank,
)
from app.ai.retrieval import (
    RERANKER_CANDIDATES,
    RRF_RANK_CONSTANT,
    RRF_RANK_WINDOW,
    RetrievedChunk,
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
LOCAL_DIR = Path(os.environ.get("STORYGUARD_LOCAL_DIR", ROOT / ".local"))
DEFAULT_RERANKER_OUTPUT = LOCAL_DIR / "experiments" / "reranker-3.4"


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


def select_queries(
    queries: list[dict], split: str | None, shard_index: int, shard_count: int
) -> list[dict]:
    if split not in {None, "dev", "test"}:
        raise ValueError("split must be dev or test")
    if shard_count < 1 or not 0 <= shard_index < shard_count:
        raise ValueError("shard_index must be between 0 and shard_count - 1")
    selected = queries if split is None else [q for q in queries if q["split"] == split]
    return selected[shard_index::shard_count]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def _write_jsonl(path: Path, metadata: dict, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in [metadata, *rows])
        + "\n"
    )
    temporary.replace(path)


def _read_jsonl(path: Path) -> tuple[dict, list[dict]]:
    values = [json.loads(line) for line in path.read_text().splitlines()]
    if not values or values[0].get("type") != "metadata":
        raise ValueError(f"Invalid shard file: {path}")
    return values[0], values[1:]


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


def experiment_data(suite_id: str | None = None) -> tuple[
    list[dict],
    list[dict],
    dict[str, list[dict[str, object]]],
    list[dict[str, object]],
    dict[str, tuple[str, str]],
    dict[str, list[str]],
    dict,
]:
    books = load("retrieval_documents.jsonl")
    queries = load("retrieval_queries.jsonl")
    if suite_id is not None:
        queries = select_suite_queries(queries, suite_id)
        selected_book_ids = {query["book_id"] for query in queries}
        books = [book for book in books if book["id"] in selected_book_ids]
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
        "chunk_count": len(all_documents),
        "qrel_count": sum(map(len, relevant_by_query.values())),
        "parser_version": PARSER_VERSION,
        "tokenizer_version": TOKENIZER_VERSION,
        "chunking": asdict(CHUNKING),
        "queries_sha256": fixture_sha256("retrieval_queries.jsonl"),
        "documents_sha256": fixture_sha256("retrieval_documents.jsonl"),
        "chunks_sha256": value_sha256(documents_by_book),
        "qrels_sha256": value_sha256(relevant_by_query),
        "ground_truth": "all same-book StoryGuard chunks containing exact evidence",
        **(
            {
                "suite_id": suite_id,
                "selected_query_ids_sha256": value_sha256(
                    [query["id"] for query in queries]
                ),
            }
            if suite_id is not None
            else {}
        ),
    }
    return (
        books,
        queries,
        documents_by_book,
        all_documents,
        scopes,
        relevant_by_query,
        dataset,
    )


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def metrics(results: list[dict]) -> dict:
    latencies = [row["latency_ms"] for row in results]
    return {
        "query_count": len(results),
        **{
            f"recall_at_{k}": statistics.fmean(
                len(set(row["retrieved_ids"][:k]) & set(row["relevant_ids"]))
                / len(row["relevant_ids"])
                for row in results
            )
            for k in (1, 5, 10, 20, 30)
        },
        "mrr_at_10": statistics.fmean(
            1 / row["rank"] if row["rank"] is not None and row["rank"] <= 10 else 0
            for row in results
        ),
        "median_latency_ms": statistics.median(latencies),
        "p50_latency_ms": _percentile(latencies, 0.5),
        "p95_latency_ms": _percentile(latencies, 0.95),
        **(
            {
                "median_reranking_latency_ms": statistics.median(
                    row["reranking_latency_ms"] for row in results
                )
            }
            if results and "reranking_latency_ms" in results[0]
            else {}
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
    }.get(strategy)
    results = []
    for query in queries:
        project_id, version_id = scopes[query["book_id"]]
        started = time.perf_counter()
        reranking_latency_ms = candidate_count = None
        if strategy == "hybrid_reranker":
            candidates = await retrieve_hybrid(
                query["query"],
                project_id,
                version_id,
                top_k=RERANKER_CANDIDATES,
            )
            candidate_count = len(candidates)
            reranking_started = time.perf_counter()
            hits = await asyncio.to_thread(
                rerank, query["query"], candidates, TOP_K
            )
            reranking_latency_ms = (time.perf_counter() - reranking_started) * 1_000
        else:
            hits = await retrieve(
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
                **(
                    {
                        "candidate_count": candidate_count,
                        "reranking_latency_ms": reranking_latency_ms,
                        "selected_count": len(hits),
                    }
                    if reranking_latency_ms is not None
                    else {}
                ),
                "top_chunks": [
                    {
                        "chunk_id": hit.chunk_id,
                        "contains_exact_evidence": query["evidence"] in hit.text,
                        "preview": " ".join(hit.text.split())[:600],
                        "rank": hit_rank,
                        "score": hit.score,
                    }
                    for hit_rank, hit in enumerate(hits[:10], 1)
                ]
                if strategy == "hybrid_reranker" or rank is None or rank > 10
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
            if any(row["split"] == split for row in results)
        },
        "all": metrics(results),
        "multiple_relevant_query_count": sum(
            len(row["relevant_ids"]) > 1 for row in results
        ),
        "non_rank_1_query_count": len(failures),
        **(
            {
                "candidate_counts": sorted(
                    {row["candidate_count"] for row in results}
                ),
                "selected_counts": sorted(
                    {row["selected_count"] for row in results}
                ),
            }
            if results and "candidate_count" in results[0]
            else {}
        ),
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


def _first_relevant_rank(retrieved_ids: list[str], relevant_ids: list[str]) -> int | None:
    ranks = [
        retrieved_ids.index(chunk_id) + 1
        for chunk_id in relevant_ids
        if chunk_id in retrieved_ids
    ]
    return min(ranks) if ranks else None


def _shard_path(output_dir: Path, shard_index: int, phase: str) -> Path:
    return output_dir / f"shard-{shard_index:02d}-{phase}.jsonl"


def _ensure_manifest(output_dir: Path, manifest: dict) -> str:
    path = output_dir / "manifest.json"
    if path.exists():
        if json.loads(path.read_text()) != manifest:
            raise ValueError("Existing experiment manifest does not match this run")
    else:
        _write_json(path, manifest)
    return value_sha256(manifest)


def _validate_shard(
    path: Path,
    manifest_sha256: str,
    shard_index: int,
    expected_query_ids: list[str],
) -> tuple[dict, list[dict]]:
    metadata, rows = _read_jsonl(path)
    if (
        metadata.get("manifest_sha256") != manifest_sha256
        or metadata.get("shard_index") != shard_index
        or [row.get("id") for row in rows] != expected_query_ids
        or any(row.get("type") != "query" for row in rows)
    ):
        raise ValueError(f"Shard validation failed: {path}")
    return metadata, rows


def _version_dir(parent: Path, fingerprint: str) -> Path:
    if len(fingerprint) != 64 or any(
        character not in "0123456789abcdef" for character in fingerprint
    ):
        raise ValueError("Invalid experiment fingerprint")
    return parent / fingerprint


def _active_candidate(output_root: Path) -> tuple[dict, Path, dict]:
    active = json.loads((output_root / "active.json").read_text())
    candidate_fingerprint = active["candidate_fingerprint"]
    candidate_dir = _version_dir(output_root, candidate_fingerprint)
    manifest = json.loads((candidate_dir / "manifest.json").read_text())
    if value_sha256(manifest) != candidate_fingerprint:
        raise ValueError("Active candidate manifest fingerprint does not match")
    return active, candidate_dir, manifest


def reranker_manifest(candidate_fingerprint: str) -> dict:
    return {
        "candidate_fingerprint": candidate_fingerprint,
        "reranker": {
            "repository": RERANKER_REPOSITORY,
            "revision": RERANKER_REVISION,
            "version": RERANKER_VERSION,
            "batch_size": RERANKER_BATCH_SIZE,
            "sentence_transformers": package_version("sentence-transformers"),
            "torch": package_version("torch"),
        },
    }


async def prepare_suite_index(suite_id: str) -> dict:
    (
        _books,
        _queries,
        documents_by_book,
        all_documents,
        scopes,
        _relevant_by_query,
        dataset,
    ) = experiment_data(suite_id)
    elasticsearch = await _request("GET", "/")
    elasticsearch_version = str(elasticsearch.json()["version"]["number"])
    fingerprint = experiment_fingerprint(
        str(dataset["chunks_sha256"]), elasticsearch_version, True
    )
    retrieval.INDEX_NAME = EXPERIMENT_INDEX_PREFIX + fingerprint
    if await experiment_index_complete(len(all_documents), True):
        return {
            "status": "already_complete",
            "experiment_index": retrieval.INDEX_NAME,
            "document_count": len(all_documents),
        }

    await delete_experiment_index()
    vectors = await asyncio.to_thread(
        embed_documents,
        [str(document["text"]) for document in all_documents],
    )
    if len(vectors) != len(all_documents):
        raise ValueError("Embedding count does not match document count")
    for document, vector in zip(all_documents, vectors, strict=True):
        document["embedding_version"] = EMBEDDING_VERSION
        document["embedding"] = vector
    for book_id, documents in documents_by_book.items():
        project_id, version_id = scopes[book_id]
        await replace_version_chunks(project_id, version_id, documents)
    if not await experiment_index_complete(len(all_documents), True):
        raise RuntimeError("Experiment index is incomplete after build")
    return {
        "status": "complete",
        "experiment_index": retrieval.INDEX_NAME,
        "document_count": len(all_documents),
    }


async def run_candidate_shard(
    output_root: Path,
    shard_index: int,
    shard_count: int,
    suite_id: str | None = None,
) -> dict:
    (
        _books,
        queries,
        _documents_by_book,
        all_documents,
        scopes,
        relevant_by_query,
        dataset,
    ) = experiment_data(suite_id)
    evaluation_queries = (
        queries
        if suite_id is not None
        else [query for query in queries if query["split"] == "test"]
    )
    selected = evaluation_queries[shard_index::shard_count]
    if not selected:
        raise ValueError("Selected experiment shard has no queries")
    elasticsearch = await _request("GET", "/")
    elasticsearch_version = str(elasticsearch.json()["version"]["number"])
    fingerprint = experiment_fingerprint(
        str(dataset["chunks_sha256"]), elasticsearch_version, True
    )
    retrieval.INDEX_NAME = EXPERIMENT_INDEX_PREFIX + fingerprint
    if not await experiment_index_complete(len(all_documents), True):
        raise RuntimeError("The fingerprinted experiment index is not complete")

    manifest = {
        "experiment_id": (
            "lesson-4.2-ai-experiment-lab"
            if suite_id is not None
            else "lesson-3.4-cross-encoder-reranker"
        ),
        "dataset": dataset,
        "evaluation_split": "dev" if suite_id is not None else "test",
        "expected_query_ids": [query["id"] for query in evaluation_queries],
        "shard_count": shard_count,
        "candidate_count": RERANKER_CANDIDATES,
        "experiment_index": retrieval.INDEX_NAME,
        "fingerprint": fingerprint,
        "elasticsearch_version": elasticsearch_version,
        "rrf": {
            "rank_constant": RRF_RANK_CONSTANT,
            "rank_window": RRF_RANK_WINDOW,
        },
        "embedding": {
            "repository": EMBEDDING_REPOSITORY,
            "revision": EMBEDDING_REVISION,
            "version": EMBEDDING_VERSION,
            "sentence_transformers": package_version("sentence-transformers"),
            "torch": package_version("torch"),
        },
        **({"evaluation_suite": suite_id} if suite_id is not None else {}),
    }
    manifest_sha256 = value_sha256(manifest)
    output_dir = _version_dir(output_root, manifest_sha256)
    if _ensure_manifest(output_dir, manifest) != manifest_sha256:
        raise ValueError("Candidate manifest fingerprint does not match")
    # ponytail: one active local run; add explicit run IDs if concurrent runs matter.
    _write_json(
        output_root / "active.json",
        {"candidate_fingerprint": manifest_sha256},
    )
    expected_query_ids = [query["id"] for query in selected]
    path = _shard_path(output_dir, shard_index, "candidates")
    if path.exists():
        metadata, rows = _validate_shard(
            path, manifest_sha256, shard_index, expected_query_ids
        )
        return {
            "status": "already_complete",
            "path": str(path),
            "query_count": len(rows),
            "model_load_ms": metadata["model_load_ms"],
        }

    started = time.perf_counter()
    await asyncio.to_thread(get_embedding_provider)
    model_load_ms = (time.perf_counter() - started) * 1_000
    rows = []
    for query in selected:
        project_id, version_id = scopes[query["book_id"]]
        started = time.perf_counter()
        candidates = await retrieve_hybrid(
            query["query"], project_id, version_id, RERANKER_CANDIDATES
        )
        retrieval_latency_ms = (time.perf_counter() - started) * 1_000
        if len(candidates) != RERANKER_CANDIDATES or any(
            candidate.project_id != project_id
            or candidate.manuscript_version_id != version_id
            for candidate in candidates
        ):
            raise RuntimeError("Candidate retrieval violated count or scope")
        candidate_ids = [candidate.chunk_id for candidate in candidates]
        relevant_ids = relevant_by_query[query["id"]]
        rows.append(
            {
                "type": "query",
                "id": query["id"],
                "book": query["title"],
                "query": query["query"],
                "relevant_ids": relevant_ids,
                "baseline_rank": _first_relevant_rank(candidate_ids, relevant_ids),
                "retrieval_latency_ms": retrieval_latency_ms,
                "candidates": [asdict(candidate) for candidate in candidates],
            }
        )
    _write_jsonl(
        path,
        {
            "type": "metadata",
            "phase": "candidates",
            "manifest_sha256": manifest_sha256,
            "shard_index": shard_index,
            "query_count": len(rows),
            "model_load_ms": model_load_ms,
        },
        rows,
    )
    return {
        "status": "complete",
        "path": str(path),
        "query_count": len(rows),
        "model_load_ms": model_load_ms,
    }


def run_rerank_shard(output_root: Path, shard_index: int) -> dict:
    _active, candidate_dir, manifest = _active_candidate(output_root)
    candidate_fingerprint = value_sha256(manifest)
    shard_count = int(manifest["shard_count"])
    if not 0 <= shard_index < shard_count:
        raise ValueError("shard_index must be between 0 and shard_count - 1")
    expected_query_ids = manifest["expected_query_ids"][shard_index::shard_count]
    candidate_path = _shard_path(candidate_dir, shard_index, "candidates")
    _candidate_metadata, candidate_rows = _validate_shard(
        candidate_path, candidate_fingerprint, shard_index, expected_query_ids
    )
    result_manifest = reranker_manifest(candidate_fingerprint)
    reranker_fingerprint = value_sha256(result_manifest)
    result_dir = _version_dir(candidate_dir / "rerankers", reranker_fingerprint)
    if _ensure_manifest(result_dir, result_manifest) != reranker_fingerprint:
        raise ValueError("Reranker manifest fingerprint does not match")
    _write_json(
        output_root / "active.json",
        {
            "candidate_fingerprint": candidate_fingerprint,
            "reranker_fingerprint": reranker_fingerprint,
        },
    )
    result_path = _shard_path(result_dir, shard_index, "results")
    if result_path.exists():
        metadata, rows = _validate_shard(
            result_path, reranker_fingerprint, shard_index, expected_query_ids
        )
        return {
            "status": "already_complete",
            "path": str(result_path),
            "query_count": len(rows),
            "model_load_ms": metadata["model_load_ms"],
        }

    started = time.perf_counter()
    get_reranker()
    model_load_ms = (time.perf_counter() - started) * 1_000
    rows = []
    for row in candidate_rows:
        candidates = [RetrievedChunk(**candidate) for candidate in row["candidates"]]
        started = time.perf_counter()
        ranked = rerank(row["query"], candidates, RERANKER_CANDIDATES)
        reranking_latency_ms = (time.perf_counter() - started) * 1_000
        candidate_ids = [candidate.chunk_id for candidate in candidates]
        reranked_ids = [candidate.chunk_id for candidate in ranked]
        scores = [candidate.score for candidate in ranked]
        if set(candidate_ids) != set(reranked_ids) or not all(
            math.isfinite(score) for score in scores
        ):
            raise RuntimeError("Reranking changed membership or returned invalid scores")
        rows.append(
            {
                "type": "query",
                "id": row["id"],
                "book": row["book"],
                "query": row["query"],
                "relevant_ids": row["relevant_ids"],
                "candidate_ids": candidate_ids,
                "reranked_ids": reranked_ids,
                "reranker_scores": scores,
                "baseline_rank": row["baseline_rank"],
                "reranker_rank": _first_relevant_rank(
                    reranked_ids, row["relevant_ids"]
                ),
                "retrieval_latency_ms": row["retrieval_latency_ms"],
                "reranking_latency_ms": reranking_latency_ms,
                "total_latency_ms": row["retrieval_latency_ms"]
                + reranking_latency_ms,
            }
        )
    _write_jsonl(
        result_path,
        {
            "type": "metadata",
            "phase": "rerank",
            "manifest_sha256": reranker_fingerprint,
            "shard_index": shard_index,
            "query_count": len(rows),
            "model_load_ms": model_load_ms,
        },
        rows,
    )
    return {
        "status": "complete",
        "path": str(result_path),
        "query_count": len(rows),
        "model_load_ms": model_load_ms,
    }


def _metrics_for(rows: list[dict], ids_key: str, latency_key: str) -> dict:
    prepared = [
        {
            "retrieved_ids": row[ids_key],
            "relevant_ids": row["relevant_ids"],
            "rank": _first_relevant_rank(row[ids_key], row["relevant_ids"]),
            "latency_ms": row[latency_key],
        }
        for row in rows
    ]
    return metrics(prepared)


def aggregate_rows(rows: list[dict]) -> dict:
    for row in rows:
        if (
            len(row["candidate_ids"]) != RERANKER_CANDIDATES
            or set(row["candidate_ids"]) != set(row["reranked_ids"])
            or len(row["reranker_scores"]) != RERANKER_CANDIDATES
            or not all(math.isfinite(score) for score in row["reranker_scores"])
        ):
            raise ValueError(f"Invalid reranker result for query {row['id']}")
    baseline = _metrics_for(rows, "candidate_ids", "retrieval_latency_ms")
    candidate = _metrics_for(rows, "reranked_ids", "total_latency_ms")
    candidate["median_reranking_latency_ms"] = statistics.median(
        row["reranking_latency_ms"] for row in rows
    )
    if baseline["recall_at_30"] != candidate["recall_at_30"]:
        raise ValueError("Recall@30 changed despite identical candidate membership")

    improvements = [
        row
        for row in rows
        if (row["reranker_rank"] or RERANKER_CANDIDATES + 1)
        < (row["baseline_rank"] or RERANKER_CANDIDATES + 1)
    ]
    regressions = [
        row
        for row in rows
        if (row["reranker_rank"] or RERANKER_CANDIDATES + 1)
        > (row["baseline_rank"] or RERANKER_CANDIDATES + 1)
    ]
    candidate_pool_misses = [row for row in rows if row["baseline_rank"] is None]

    def examples(selected: list[dict]) -> list[dict]:
        return [
            {
                "id": row["id"],
                "book": row["book"],
                "query": row["query"],
                "baseline_rank": row["baseline_rank"],
                "reranker_rank": row["reranker_rank"],
                "top_10": [
                    {"chunk_id": chunk_id, "score": score}
                    for chunk_id, score in zip(
                        row["reranked_ids"][:10],
                        row["reranker_scores"][:10],
                        strict=True,
                    )
                ],
            }
            for row in selected[:3]
        ]

    return {
        "query_count": len(rows),
        "strategies": {"hybrid": baseline, "hybrid_reranker": candidate},
        "rank_change_count": sum(
            row["baseline_rank"] != row["reranker_rank"] for row in rows
        ),
        "improvement_count": len(improvements),
        "improvement_examples": examples(improvements),
        "regression_count": len(regressions),
        "regression_examples": examples(regressions),
        "candidate_pool_miss_count": len(candidate_pool_misses),
        "candidate_pool_miss_examples": examples(candidate_pool_misses),
    }


def aggregate_shards(output_root: Path) -> dict:
    active, candidate_dir, manifest = _active_candidate(output_root)
    candidate_fingerprint = value_sha256(manifest)
    reranker_fingerprint = active.get("reranker_fingerprint")
    if not isinstance(reranker_fingerprint, str):
        raise ValueError("No active reranker results")
    result_dir = _version_dir(candidate_dir / "rerankers", reranker_fingerprint)
    result_manifest = json.loads((result_dir / "manifest.json").read_text())
    if (
        value_sha256(result_manifest) != reranker_fingerprint
        or result_manifest.get("candidate_fingerprint") != candidate_fingerprint
    ):
        raise ValueError("Active reranker manifest fingerprint does not match")
    expected_query_ids = manifest["expected_query_ids"]
    shard_count = int(manifest["shard_count"])
    rows = []
    model_loads = {"embedding_ms": [], "reranker_ms": []}
    for shard_index in range(shard_count):
        shard_ids = expected_query_ids[shard_index::shard_count]
        candidate_metadata, candidate_rows = _validate_shard(
            _shard_path(candidate_dir, shard_index, "candidates"),
            candidate_fingerprint,
            shard_index,
            shard_ids,
        )
        result_metadata, result_rows = _validate_shard(
            _shard_path(result_dir, shard_index, "results"),
            reranker_fingerprint,
            shard_index,
            shard_ids,
        )
        if [row["id"] for row in candidate_rows] != [
            row["id"] for row in result_rows
        ]:
            raise ValueError(f"Candidate/result mismatch in shard {shard_index}")
        rows.extend(result_rows)
        model_loads["embedding_ms"].append(candidate_metadata["model_load_ms"])
        model_loads["reranker_ms"].append(result_metadata["model_load_ms"])
    if len(rows) != len(expected_query_ids) or set(row["id"] for row in rows) != set(
        expected_query_ids
    ):
        raise ValueError("Aggregated query coverage is incomplete or duplicated")
    aggregate = {
        "candidate_fingerprint": candidate_fingerprint,
        "reranker_fingerprint": reranker_fingerprint,
        "dataset": manifest["dataset"],
        "evaluation_split": manifest["evaluation_split"],
        "experiment_index": manifest["experiment_index"],
        "fingerprint": manifest["fingerprint"],
        "embedding": manifest["embedding"],
        "reranker": result_manifest["reranker"],
        "model_loads": model_loads,
        **aggregate_rows(rows),
    }
    _write_json(result_dir / "aggregate.json", aggregate)
    return aggregate


async def run(
    strategy: str = "bm25",
    *,
    split: str | None = None,
    shard_index: int = 0,
    shard_count: int = 1,
) -> dict:
    if strategy not in {"bm25", "vector", "hybrid", "hybrid_reranker", "compare"}:
        raise ValueError(
            "strategy must be bm25, vector, hybrid, hybrid_reranker, or compare"
        )
    (
        _books,
        all_queries,
        documents_by_book,
        all_documents,
        scopes,
        relevant_by_query,
        dataset,
    ) = experiment_data()

    queries = select_queries(all_queries, split, shard_index, shard_count)
    if not queries:
        raise ValueError("Selected experiment shard has no queries")

    dataset = {
        **dataset,
        "evaluation": {
            "split": split or "all",
            "shard_index": shard_index,
            "shard_count": shard_count,
            "query_count": len(queries),
        },
    }
    require_embeddings = strategy in {
        "vector",
        "hybrid",
        "hybrid_reranker",
        "compare",
    }
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
    reranker_load_ms = None
    if strategy in {"hybrid_reranker", "compare"}:
        started = time.perf_counter()
        await asyncio.to_thread(get_reranker)
        reranker_load_ms = (time.perf_counter() - started) * 1_000
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
    if strategy in {"hybrid_reranker", "compare"}:
        results_by_strategy["hybrid_reranker"] = await evaluate(
            "hybrid_reranker", queries, scopes, relevant_by_query
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
            row["latency_ms"] for row in (vector_results[1:] or vector_results)
        )
    if "hybrid" in reports:
        reports["hybrid"]["rrf"] = {
            "rank_constant": RRF_RANK_CONSTANT,
            "rank_window": RRF_RANK_WINDOW,
        }
        reports["hybrid"]["embedding"] = embedding_stats
    if "hybrid_reranker" in reports:
        reports["hybrid_reranker"]["rrf"] = {
            "rank_constant": RRF_RANK_CONSTANT,
            "rank_window": RRF_RANK_WINDOW,
        }
        reports["hybrid_reranker"]["embedding"] = embedding_stats
        reports["hybrid_reranker"]["reranker"] = {
            "provider": "sentence_transformers",
            "repository": RERANKER_REPOSITORY,
            "revision": RERANKER_REVISION,
            "version": RERANKER_VERSION,
            "model_load_ms": reranker_load_ms,
            "batch_size": RERANKER_BATCH_SIZE,
        }
    if strategy != "compare":
        return reports[strategy]

    results = [
        {
            "book": bm25["book"],
            "query": bm25["query"],
            "bm25_rank": bm25["rank"],
            "vector_rank": vector["rank"],
            "hybrid_rank": hybrid["rank"],
            "reranker_rank": hybrid_reranker["rank"],
            "reranker_top_chunks": hybrid_reranker["top_chunks"],
        }
        for bm25, vector, hybrid, hybrid_reranker in zip(
            results_by_strategy["bm25"],
            results_by_strategy["vector"],
            results_by_strategy["hybrid"],
            results_by_strategy["hybrid_reranker"],
            strict=True,
        )
    ]
    summaries = {
        name: {
            "strategy": strategy_report["strategy"],
            "splits": strategy_report["splits"],
            "all": strategy_report["all"],
            "non_rank_1_query_count": strategy_report["non_rank_1_query_count"],
            "latencies_ms": [
                row["latency_ms"] for row in results_by_strategy[name]
            ],
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
            **(
                {
                    "candidate_counts": strategy_report["candidate_counts"],
                    "selected_counts": strategy_report["selected_counts"],
                }
                if name == "hybrid_reranker"
                else {}
            ),
            **(
                {
                    "reranking_latencies_ms": [
                        row["reranking_latency_ms"]
                        for row in results_by_strategy[name]
                    ]
                }
                if name == "hybrid_reranker"
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
    reranker_improvements = [
        row
        for row in results
        if (row["reranker_rank"] or TOP_K + 1)
        < (row["hybrid_rank"] or TOP_K + 1)
    ]
    reranker_regressions = [
        row
        for row in results
        if (row["reranker_rank"] or TOP_K + 1)
        > (row["hybrid_rank"] or TOP_K + 1)
    ]
    return {
        "dataset": dataset,
        "document_cache": cache_stats,
        "embedding": embedding_stats,
        "rrf": reports["hybrid"]["rrf"],
        "reranker": reports["hybrid_reranker"]["reranker"],
        "strategies": summaries,
        "hybrid_rank_change_count": sum(
            row["bm25_rank"] != row["hybrid_rank"] for row in results
        ),
        "hybrid_improvement_count": len(improvements),
        "hybrid_improvement_examples": improvements[:10],
        "hybrid_regression_count": len(regressions),
        "hybrid_regression_examples": regressions[:10],
        "reranker_rank_change_count": sum(
            row["hybrid_rank"] != row["reranker_rank"] for row in results
        ),
        "reranker_improvement_count": len(reranker_improvements),
        "reranker_improvement_examples": reranker_improvements[:3],
        "reranker_regression_count": len(reranker_regressions),
        "reranker_regression_examples": reranker_regressions[:3],
        "candidate_pool_miss_count": sum(
            row["hybrid_rank"] is None for row in results
        ),
        "anne_diagnostic": next(
            (row for row in results if "correct spelling" in row["query"]), None
        ),
    }


def cli_result(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict:
    if args.phase == "prepare":
        if args.suite is None:
            parser.error("--suite is required for the prepare phase")
        return asyncio.run(prepare_suite_index(args.suite))
    if args.phase == "candidates":
        return asyncio.run(
            run_candidate_shard(
                args.output_dir,
                args.shard_index,
                args.shard_count,
                args.suite,
            )
        )
    if args.phase == "rerank":
        return run_rerank_shard(args.output_dir, args.shard_index)
    if args.phase == "aggregate":
        aggregate = aggregate_shards(args.output_dir)
        active = json.loads((args.output_dir / "active.json").read_text())
        return {
            "status": "complete",
            "path": str(
                _version_dir(args.output_dir, active["candidate_fingerprint"])
                / "rerankers"
                / active["reranker_fingerprint"]
                / "aggregate.json"
            ),
            "query_count": aggregate["query_count"],
        }
    if args.suite is not None:
        parser.error("--suite requires a phased experiment")
    return asyncio.run(
        run(
            args.strategy,
            split=args.split,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase", choices=("prepare", "candidates", "rerank", "aggregate")
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RERANKER_OUTPUT)
    parser.add_argument("--suite", choices=tuple(SUITES))
    parser.add_argument(
        "--strategy",
        choices=("bm25", "vector", "hybrid", "hybrid_reranker", "compare"),
        default="bm25",
    )
    parser.add_argument("--split", choices=("dev", "test"))
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--experiment-run-id", type=uuid.UUID)
    parser.add_argument("--trace-id", type=uuid.UUID)
    args = parser.parse_args()
    if args.trace_id is not None:
        if args.phase is None or args.experiment_run_id is None:
            parser.error("--trace-id requires --phase and --experiment-run-id")
        with trace(
            name=f"storyguard.experiment.{args.phase}",
            inputs={
                "suite": args.suite,
                "shard_index": args.shard_index,
                "shard_count": args.shard_count,
            },
            run_type="chain",
            run_id=args.trace_id,
            tags=["ai-experiment-lab", args.phase],
            metadata={
                "experiment_run_id": str(args.experiment_run_id),
                "diagnostic_only": True,
            },
        ) as root_run:
            result = cli_result(args, parser)
            root_run.end(
                outputs={
                    key: value
                    for key, value in result.items()
                    if key in {"status", "query_count", "document_count"}
                }
            )
        result["trace_id"] = str(args.trace_id)
    else:
        result = cli_result(args, parser)
    print(json.dumps(result, indent=2))
