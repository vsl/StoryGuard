import os
import unittest
import uuid
from unittest.mock import AsyncMock, patch

import httpx

from app.ai.retrieval import replace_version_chunks, retrieve_bm25


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


class RetrievalTest(unittest.IsolatedAsyncioTestCase):
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
        current = document(self.project_a, self.current_version, "Zephyra current")
        await replace_version_chunks(self.project_a, self.current_version, [current])
        await replace_version_chunks(
            self.project_a,
            self.old_version,
            [document(self.project_a, self.old_version, "Zephyra old")],
        )
        await replace_version_chunks(
            self.project_b,
            self.current_version,
            [document(self.project_b, self.current_version, "Zephyra other project")],
        )

        hits = await retrieve_bm25(
            "Zephyra", self.project_a, self.current_version
        )
        self.assertEqual([hit.chunk_id for hit in hits], [current["chunk_id"]])

        replacement = document(self.project_a, self.current_version, "BMW replacement")
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
