import os
import unittest
import uuid
from unittest.mock import AsyncMock, patch

import httpx

from app.ai.embeddings import (
    EMBEDDING_DIMENSION,
    EMBEDDING_VERSION,
    LocalEmbeddingProvider,
)
from app.ai.reranking import LocalCrossEncoderReranker
from app.ai.retrieval import (
    RERANKER_CANDIDATES,
    RetrievedChunk,
    replace_version_chunks,
    retrieve_bm25,
    retrieve_hybrid,
    retrieve_hybrid_reranked,
    retrieve_vector,
)
from scripts import bm25_experiment


def response(payload: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        json=payload,
        request=httpx.Request("POST", "http://elasticsearch.test"),
    )


def document(project_id: str, version_id: str, text: str) -> dict[str, object]:
    chunk_id = str(uuid.uuid4())
    return {
        "chunk_id": chunk_id,
        "project_id": project_id,
        "manuscript_version_id": version_id,
        "chapter_id": str(uuid.uuid4()),
        "chapter_ordinal": 1,
        "scene_id": None,
        "text": text,
        "content_hash": chunk_id.replace("-", ""),
    }


def vector(first: float = 1.0) -> list[float]:
    return [first, *([0.0] * (EMBEDDING_DIMENSION - 1))]


def embedded_document(
    project_id: str, version_id: str, text: str, first: float = 1.0
) -> dict[str, object]:
    result = document(project_id, version_id, text)
    result.update(
        embedding_version=EMBEDDING_VERSION,
        embedding=vector(first),
    )
    return result


def retrieved(chunk_id: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        project_id="project",
        manuscript_version_id="version",
        chapter_id="chapter",
        chapter_ordinal=1,
        scene_id=None,
        text=chunk_id,
        content_hash=chunk_id,
        score=1,
    )


class FakeEmbeddingModel:
    def encode_document(self, texts, **_kwargs):
        return [vector() for _ in texts]

    def encode_query(self, _text, **_kwargs):
        return vector()


class FakeRerankerModel:
    def __init__(self, scores) -> None:
        self.scores = scores
        self.inputs = None

    def predict(self, inputs, **_kwargs):
        self.inputs = inputs
        return self.scores


class RetrievalTest(unittest.IsolatedAsyncioTestCase):
    def test_experiment_queries_are_deterministically_sharded(self) -> None:
        queries = [
            {"id": str(index), "split": "test" if index < 5 else "dev"}
            for index in range(7)
        ]
        shards = [
            bm25_experiment.select_queries(queries, "test", index, 2)
            for index in range(2)
        ]
        self.assertEqual(
            [[query["id"] for query in shard] for shard in shards],
            [["0", "2", "4"], ["1", "3"]],
        )
        with self.assertRaisesRegex(ValueError, "shard_index"):
            bm25_experiment.select_queries(queries, None, 2, 2)

    def test_reranker_shards_aggregate_exact_rows(self) -> None:
        first_candidates = ["b", "a", *[f"x-{index}" for index in range(28)]]
        second_candidates = ["c", "d", *[f"y-{index}" for index in range(28)]]
        rows = [
            {
                "id": "improvement",
                "book": "Book",
                "query": "first",
                "relevant_ids": ["a"],
                "candidate_ids": first_candidates,
                "reranked_ids": ["a", "b", *first_candidates[2:]],
                "reranker_scores": list(range(30, 0, -1)),
                "baseline_rank": 2,
                "reranker_rank": 1,
                "retrieval_latency_ms": 10,
                "reranking_latency_ms": 90,
                "total_latency_ms": 100,
            },
            {
                "id": "regression",
                "book": "Book",
                "query": "second",
                "relevant_ids": ["c"],
                "candidate_ids": second_candidates,
                "reranked_ids": ["d", "c", *second_candidates[2:]],
                "reranker_scores": list(range(30, 0, -1)),
                "baseline_rank": 1,
                "reranker_rank": 2,
                "retrieval_latency_ms": 20,
                "reranking_latency_ms": 80,
                "total_latency_ms": 100,
            },
        ]

        aggregate = bm25_experiment.aggregate_rows(rows)

        self.assertEqual(aggregate["query_count"], 2)
        self.assertEqual(aggregate["improvement_count"], 1)
        self.assertEqual(aggregate["regression_count"], 1)
        self.assertEqual(
            aggregate["strategies"]["hybrid"]["recall_at_30"],
            aggregate["strategies"]["hybrid_reranker"]["recall_at_30"],
        )
        self.assertEqual(
            aggregate["strategies"]["hybrid"]["mrr_at_10"], 0.75
        )

    def test_experiment_fingerprint_tracks_retrieval_inputs(self) -> None:
        fingerprint = bm25_experiment.experiment_fingerprint(
            "a" * 64, "8.19.19", True
        )
        self.assertEqual(
            fingerprint,
            bm25_experiment.experiment_fingerprint(
                "a" * 64, "8.19.19", True
            ),
        )
        self.assertNotEqual(
            fingerprint,
            bm25_experiment.experiment_fingerprint(
                "b" * 64, "8.19.19", True
            ),
        )
        self.assertNotEqual(
            fingerprint,
            bm25_experiment.experiment_fingerprint(
                "a" * 64, "8.19.19", False
            ),
        )
        with patch.object(bm25_experiment, "EMBEDDING_VERSION", "changed"):
            self.assertNotEqual(
                fingerprint,
                bm25_experiment.experiment_fingerprint(
                    "a" * 64, "8.19.19", True
                ),
            )

    def test_reranker_cache_is_versioned_after_candidates(self) -> None:
        candidate_fingerprint = "a" * 64
        manifest = bm25_experiment.reranker_manifest(candidate_fingerprint)

        with patch.object(bm25_experiment, "RERANKER_REVISION", "changed"):
            changed = bm25_experiment.reranker_manifest(candidate_fingerprint)

        self.assertEqual(
            manifest["candidate_fingerprint"], candidate_fingerprint
        )
        self.assertEqual(
            changed["candidate_fingerprint"], candidate_fingerprint
        )
        self.assertNotEqual(
            bm25_experiment.value_sha256(manifest),
            bm25_experiment.value_sha256(changed),
        )

    async def test_experiment_cache_requires_all_embeddings(self) -> None:
        with patch.object(
            bm25_experiment,
            "_request",
            new=AsyncMock(side_effect=[response({"count": 2}), response({"count": 2})]),
        ):
            self.assertTrue(
                await bm25_experiment.experiment_index_complete(2, True)
            )
        with patch.object(
            bm25_experiment,
            "_request",
            new=AsyncMock(side_effect=[response({"count": 2}), response({"count": 1})]),
        ):
            self.assertFalse(
                await bm25_experiment.experiment_index_complete(2, True)
            )

    def test_local_provider_uses_query_and_document_encoders(self) -> None:
        provider = LocalEmbeddingProvider(FakeEmbeddingModel())
        self.assertEqual(len(provider.embed_query("car")), EMBEDDING_DIMENSION)
        self.assertEqual(
            len(provider.embed_documents(["BMW"])[0]), EMBEDDING_DIMENSION
        )

    async def test_bm25_query_is_scoped_and_preserves_ranking(self) -> None:
        project_id, version_id = str(uuid.uuid4()), str(uuid.uuid4())
        sources = [
            document(project_id, version_id, "Zephyra appears once."),
            document(project_id, version_id, "Zephyra appears later."),
        ]
        hits = [
            {"_score": score, "_source": source}
            for score, source in zip((4.2, 2.1), sources, strict=True)
        ]
        with patch(
            "app.ai.retrieval._request",
            new=AsyncMock(return_value=response({"hits": {"hits": hits}})),
        ) as request:
            results = await retrieve_bm25(" Zephyra ", project_id, version_id, 2)

        body = request.await_args.kwargs["json"]
        self.assertEqual(
            body["query"]["bool"]["filter"],
            [
                {"term": {"project_id": project_id}},
                {"term": {"manuscript_version_id": version_id}},
            ],
        )
        self.assertEqual(body["size"], 2)
        self.assertEqual(body["sort"], [{"_score": "desc"}, {"chunk_id": "asc"}])
        self.assertEqual([result.chunk_id for result in results], [s["chunk_id"] for s in sources])
        self.assertEqual([result.score for result in results], [4.2, 2.1])

    async def test_vector_query_is_scoped_to_compatible_embeddings(self) -> None:
        project_id, version_id = str(uuid.uuid4()), str(uuid.uuid4())
        source = embedded_document(project_id, version_id, "BMW replacement")
        source.pop("embedding")
        with (
            patch("app.ai.retrieval.embed_query", return_value=vector()),
            patch(
                "app.ai.retrieval._request",
                new=AsyncMock(
                    return_value=response(
                        {"hits": {"hits": [{"_score": 0.9, "_source": source}]}}
                    )
                ),
            ) as request,
        ):
            results = await retrieve_vector(" car ", project_id, version_id, 1)

        body = request.await_args.kwargs["json"]
        self.assertEqual(body["knn"]["k"], 1)
        self.assertEqual(body["knn"]["num_candidates"], 100)
        self.assertEqual(
            body["knn"]["filter"]["bool"]["filter"],
            [
                {"term": {"project_id": project_id}},
                {"term": {"manuscript_version_id": version_id}},
                {"term": {"embedding_version": EMBEDDING_VERSION}},
            ],
        )
        self.assertEqual(results[0].chunk_id, source["chunk_id"])

    async def test_hybrid_fuses_unique_chunks_by_rank(self) -> None:
        with (
            patch(
                "app.ai.retrieval.retrieve_bm25",
                new=AsyncMock(return_value=[retrieved("a"), retrieved("shared")]),
            ) as bm25,
            patch(
                "app.ai.retrieval.retrieve_vector",
                new=AsyncMock(return_value=[retrieved("b"), retrieved("shared")]),
            ) as vector_search,
        ):
            results = await retrieve_hybrid(
                "query", "project", "version", 3, rank_constant=60, rank_window=3
            )

        bm25.assert_awaited_once_with("query", "project", "version", 3)
        vector_search.assert_awaited_once_with("query", "project", "version", 3)
        self.assertEqual(
            [result.chunk_id for result in results], ["shared", "a", "b"]
        )
        self.assertAlmostEqual(results[0].score, 2 / 62)
        self.assertEqual(results[1].score, results[2].score)

        with self.assertRaisesRegex(ValueError, "rank_window"):
            await retrieve_hybrid("query", "project", "version", 3, rank_window=2)

    def test_cross_encoder_reranks_candidates_with_stable_ties(self) -> None:
        model = FakeRerankerModel([0.1, 0.9, 0.9])
        reranker = LocalCrossEncoderReranker(model)
        candidates = [retrieved(chunk_id) for chunk_id in ("c", "b", "a")]

        results = reranker.rerank(" query ", candidates, 2)

        self.assertEqual(
            model.inputs, [("query", "c"), ("query", "b"), ("query", "a")]
        )
        self.assertEqual([result.chunk_id for result in results], ["a", "b"])
        self.assertEqual([result.score for result in results], [0.9, 0.9])
        self.assertEqual(results[0].project_id, "project")

        with self.assertRaisesRegex(ValueError, "one finite score"):
            LocalCrossEncoderReranker(FakeRerankerModel([float("nan")])).rerank(
                "query", candidates, 2
            )

    async def test_hybrid_reranker_uses_bounded_candidate_pool(self) -> None:
        candidates = [retrieved(chunk_id) for chunk_id in ("a", "b", "c")]
        selected = candidates[:2]
        with (
            patch(
                "app.ai.retrieval.retrieve_hybrid",
                new=AsyncMock(return_value=candidates),
            ) as hybrid,
            patch("app.ai.reranking.rerank", return_value=selected) as rerank,
        ):
            results = await retrieve_hybrid_reranked(
                "query", "project", "version", top_k=2
            )

        hybrid.assert_awaited_once_with(
            "query", "project", "version", top_k=RERANKER_CANDIDATES
        )
        rerank.assert_called_once_with("query", candidates, 2)
        self.assertEqual(results, selected)

    async def test_inputs_and_index_documents_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            await retrieve_bm25(" ", "project", "version")
        with self.assertRaisesRegex(ValueError, "between 1 and 100"):
            await retrieve_bm25("query", "project", "version", 0)
        with self.assertRaisesRegex(ValueError, "must match"):
            await replace_version_chunks(
                "project-a",
                "version-a",
                [document("project-b", "version-a", "wrong scope")],
            )
        invalid = embedded_document("project", "version", "bad vector")
        invalid["embedding"] = [float("nan")] * EMBEDDING_DIMENSION
        with self.assertRaisesRegex(ValueError, "finite dimensions"):
            await replace_version_chunks("project", "version", [invalid])

    async def test_partial_bulk_failure_is_rejected(self) -> None:
        project_id, version_id = str(uuid.uuid4()), str(uuid.uuid4())
        with patch(
            "app.ai.retrieval._request",
            new=AsyncMock(
                side_effect=[
                    response({"acknowledged": True}),
                    response({"deleted": 0}),
                    response({"errors": True}),
                ]
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "rejected"):
                await replace_version_chunks(
                    project_id,
                    version_id,
                    [document(project_id, version_id, "text")],
                )


RUN_ELASTICSEARCH_TESTS = os.environ.get("RUN_ELASTICSEARCH_TESTS") == "1"


@unittest.skipUnless(RUN_ELASTICSEARCH_TESTS, "set RUN_ELASTICSEARCH_TESTS=1")
class ElasticsearchIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.project_a, self.project_b = str(uuid.uuid4()), str(uuid.uuid4())
        self.current_version, self.old_version = str(uuid.uuid4()), str(uuid.uuid4())

    async def asyncTearDown(self) -> None:
        for project_id, version_id in (
            (self.project_a, self.current_version),
            (self.project_a, self.old_version),
            (self.project_b, self.current_version),
        ):
            await replace_version_chunks(project_id, version_id, [])

    async def test_scope_isolation_and_version_replacement(self) -> None:
        current = embedded_document(
            self.project_a, self.current_version, "Zephyra current"
        )
        await replace_version_chunks(self.project_a, self.current_version, [current])
        await replace_version_chunks(
            self.project_a,
            self.old_version,
            [embedded_document(self.project_a, self.old_version, "Zephyra old")],
        )
        await replace_version_chunks(
            self.project_b,
            self.current_version,
            [
                embedded_document(
                    self.project_b,
                    self.current_version,
                    "Zephyra other project",
                )
            ],
        )

        hits = await retrieve_bm25(
            "Zephyra", self.project_a, self.current_version
        )
        self.assertEqual([hit.chunk_id for hit in hits], [current["chunk_id"]])

        with patch("app.ai.retrieval.embed_query", return_value=vector()):
            vector_hits = await retrieve_vector(
                "semantic Zephyra", self.project_a, self.current_version
            )
        self.assertEqual([hit.chunk_id for hit in vector_hits], [current["chunk_id"]])

        with patch("app.ai.retrieval.embed_query", return_value=vector()):
            hybrid_hits = await retrieve_hybrid(
                "Zephyra", self.project_a, self.current_version
            )
        self.assertEqual([hit.chunk_id for hit in hybrid_hits], [current["chunk_id"]])

        replacement = embedded_document(
            self.project_a, self.current_version, "BMW replacement"
        )
        await replace_version_chunks(
            self.project_a, self.current_version, [replacement]
        )
        self.assertEqual(
            await retrieve_bm25("Zephyra", self.project_a, self.current_version), []
        )
        self.assertEqual(
            [
                hit.chunk_id
                for hit in await retrieve_bm25(
                    "BMW", self.project_a, self.current_version
                )
            ],
            [replacement["chunk_id"]],
        )


if __name__ == "__main__":
    unittest.main()
