import asyncio
import json
import math
import os
from dataclasses import dataclass

import httpx

from app.ai.embeddings import (
    EMBEDDING_DIMENSION,
    EMBEDDING_VERSION,
    embed_query,
)


INDEX_NAME = os.environ.get("STORYGUARD_CHUNK_INDEX", "storyguard-chunks-v2")
INDEX_MAPPING = {
    "mappings": {
        "dynamic": "strict",
        "properties": {
            "chunk_id": {"type": "keyword"},
            "project_id": {"type": "keyword"},
            "manuscript_version_id": {"type": "keyword"},
            "chapter_id": {"type": "keyword"},
            "chapter_ordinal": {"type": "integer"},
            "scene_id": {"type": "keyword"},
            "text": {"type": "text"},
            "content_hash": {"type": "keyword"},
            "embedding_version": {"type": "keyword"},
            "embedding": {
                "type": "dense_vector",
                "dims": EMBEDDING_DIMENSION,
                "similarity": "cosine",
            },
        },
    }
}


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    project_id: str
    manuscript_version_id: str
    chapter_id: str
    chapter_ordinal: int
    scene_id: str | None
    text: str
    content_hash: str
    score: float
    embedding_version: str | None = None


async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    url = f"{os.environ['ELASTICSEARCH_URL'].rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=10) as client:
        for attempt in range(3):
            try:
                response = await client.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                if attempt == 2:
                    raise ConnectionError("Elasticsearch request failed") from exc
            else:
                if response.status_code < 500 and response.status_code != 429:
                    response.raise_for_status()
                    return response
                if attempt == 2:
                    raise ConnectionError(
                        f"Elasticsearch returned HTTP {response.status_code}"
                    )
            await asyncio.sleep(0.05 * (attempt + 1))
    raise AssertionError("unreachable")


async def ensure_index() -> None:
    try:
        await _request("PUT", f"/{INDEX_NAME}", json=INDEX_MAPPING)
    except httpx.HTTPStatusError as exc:
        error = exc.response.json().get("error", {})
        if not (
            exc.response.status_code == 400
            and error.get("type") == "resource_already_exists_exception"
        ):
            raise


async def replace_version_chunks(
    project_id: str, manuscript_version_id: str, documents: list[dict[str, object]]
) -> None:
    project_id, manuscript_version_id = str(project_id), str(manuscript_version_id)
    if any(
        str(document.get("project_id")) != project_id
        or str(document.get("manuscript_version_id")) != manuscript_version_id
        for document in documents
    ):
        raise ValueError("Indexed chunks must match the requested project and version")
    for document in documents:
        vector = document.get("embedding")
        if vector is None:
            continue
        if document.get("embedding_version") != EMBEDDING_VERSION:
            raise ValueError("Indexed embedding version is incompatible")
        if (
            not isinstance(vector, list)
            or len(vector) != EMBEDDING_DIMENSION
            or not all(
                isinstance(value, (int, float)) and math.isfinite(value)
                for value in vector
            )
        ):
            raise ValueError(
                f"Indexed embeddings must have {EMBEDDING_DIMENSION} finite dimensions"
            )

    await ensure_index()
    scope = [
        {"term": {"project_id": project_id}},
        {"term": {"manuscript_version_id": manuscript_version_id}},
    ]
    await _request(
        "POST",
        f"/{INDEX_NAME}/_delete_by_query?refresh=true&conflicts=proceed",
        json={"query": {"bool": {"filter": scope}}},
    )
    if not documents:
        return

    lines = []
    for document in documents:
        lines.extend(
            (
                json.dumps(
                    {"index": {"_index": INDEX_NAME, "_id": document["chunk_id"]}},
                    separators=(",", ":"),
                ),
                json.dumps(document, separators=(",", ":")),
            )
        )
    response = await _request(
        "POST",
        "/_bulk?refresh=wait_for",
        content="\n".join(lines) + "\n",
        headers={"content-type": "application/x-ndjson"},
    )
    if response.json().get("errors"):
        raise RuntimeError("Elasticsearch rejected one or more chunks")


async def retrieve_bm25(
    query: str, project_id: str, manuscript_version_id: str, top_k: int = 30
) -> list[RetrievedChunk]:
    query = query.strip()
    if not query:
        raise ValueError("Retrieval query must not be empty")
    if not 1 <= top_k <= 100:
        raise ValueError("top_k must be between 1 and 100")

    response = await _request(
        "POST",
        f"/{INDEX_NAME}/_search",
        json={
            "size": top_k,
            "_source": {"excludes": ["embedding"]},
            "sort": [{"_score": "desc"}, {"chunk_id": "asc"}],
            "query": {
                "bool": {
                    "must": [{"match": {"text": {"query": query}}}],
                    "filter": [
                        {"term": {"project_id": str(project_id)}},
                        {
                            "term": {
                                "manuscript_version_id": str(manuscript_version_id)
                            }
                        },
                    ],
                }
            },
        },
    )
    return [
        RetrievedChunk(score=float(hit.get("_score") or 0), **hit["_source"])
        for hit in response.json()["hits"]["hits"]
    ]


async def retrieve_vector(
    query: str, project_id: str, manuscript_version_id: str, top_k: int = 30
) -> list[RetrievedChunk]:
    query = query.strip()
    if not query:
        raise ValueError("Retrieval query must not be empty")
    if not 1 <= top_k <= 100:
        raise ValueError("top_k must be between 1 and 100")

    query_vector = await asyncio.to_thread(embed_query, query)
    response = await _request(
        "POST",
        f"/{INDEX_NAME}/_search",
        json={
            "size": top_k,
            "_source": {"excludes": ["embedding"]},
            "knn": {
                "field": "embedding",
                "query_vector": query_vector,
                "k": top_k,
                "num_candidates": max(100, top_k),
                "filter": {
                    "bool": {
                        "filter": [
                            {"term": {"project_id": str(project_id)}},
                            {
                                "term": {
                                    "manuscript_version_id": str(
                                        manuscript_version_id
                                    )
                                }
                            },
                            {"term": {"embedding_version": EMBEDDING_VERSION}},
                        ]
                    }
                },
            },
        },
    )
    results = [
        RetrievedChunk(score=float(hit.get("_score") or 0), **hit["_source"])
        for hit in response.json()["hits"]["hits"]
    ]
    return sorted(results, key=lambda result: (-result.score, result.chunk_id))
