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
from app.ai.retrieval import replace_version_chunks, retrieve_bm25, retrieve_vector


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


class FakeEmbeddingModel:
    def encode_document(self, texts, **_kwargs):
        return [vector() for _ in texts]

    def encode_query(self, _text, **_kwargs):
        return vector()


class RetrievalTest(unittest.IsolatedAsyncioTestCase):
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
