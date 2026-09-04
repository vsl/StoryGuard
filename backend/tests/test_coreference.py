import hashlib
import asyncio
import json
import tempfile
import uuid
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from langsmith import tracing_context

from app.ai.coreference import MODEL, REVISION, PIPELINE, load_coreference, same_cluster, validate_cache
from tests.test_retrieval import FakeTraceClient


class CoreferenceTest(unittest.TestCase):
    def test_original_text_exact_spans_and_window_local_identity(self):
        text = "Nora met Nori."
        doc = {"text_sha256": hashlib.sha256(text.encode()).hexdigest(),
               "windows": [{"clusters": [[[0, 4], [9, 13]]]}]}
        self.assertTrue(same_cluster(doc, text, (0, 4), (9, 13)))
        self.assertFalse(same_cluster(doc, text, (0, 4), (9, 12)))
        with self.assertRaises(ValueError):
            same_cluster(doc, "Other source", (0, 4), (9, 13))
        doc["windows"] = [{"clusters": [[[0, 4]]]}, {"clusters": [[[9, 13]]]}]
        self.assertFalse(same_cluster(doc, text, (0, 4), (9, 13)))
        doc["windows"] = [{"clusters": [[[0, 4], [9, 13]], [[0, 4]]]}]
        self.assertFalse(same_cluster(doc, text, (0, 4), (9, 13)))
        for invalid in ([False, 4], [0, 999], [-1, 4], [4, 0]):
            doc["windows"] = [{"clusters": [[invalid]]}]
            with self.assertRaises(ValueError):
                same_cluster(doc, text, (0, 4), (9, 13))


class CoreferenceRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_cache_scope_hit_and_subprocess_stop(self):
        text = "Nora met Nori."
        documents = [{"id": str(uuid.uuid4()), "text": text}]
        cache = {"model": MODEL, "revision": REVISION, "pipeline": PIPELINE,
                 "documents": [{"id": documents[0]["id"], "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                                "windows": [{"clusters": [[[0, 4], [9, 13]]]}]}]}
        validate_cache(cache, documents)
        with self.assertRaises(ValueError):
            validate_cache(cache, [{"id": "different-chapter", "text": text}])
        with self.assertRaises(ValueError):
            validate_cache({**cache, "revision": "stale"}, documents)
        check = AsyncMock()
        completed = Mock(returncode=0, wait=AsyncMock(return_value=0))
        async def spawn(*args, **kwargs):
            Path(args[args.index("--output") + 1]).write_text(json.dumps(cache))
            self.assertNotIn("DATABASE_URL", kwargs["env"])
            return completed
        trace_client = FakeTraceClient()
        with tracing_context(enabled=True, client=trace_client), tempfile.TemporaryDirectory() as root, patch.dict("os.environ", {"STORYGUARD_LOCAL_DIR": root}), patch(
            "app.ai.coreference.asyncio.create_subprocess_exec", new=AsyncMock(side_effect=spawn)
        ) as create:
            version = uuid.uuid4()
            self.assertFalse((await load_coreference(version, documents, check))["cache_hit"])
            self.assertTrue((await load_coreference(version, documents, check))["cache_hit"])
            self.assertEqual(create.await_count, 1)
            await load_coreference(uuid.uuid4(), documents, check)
            self.assertEqual(create.await_count, 2)  # Never reuse another version's cache.

            process = Mock(returncode=None)
            exited = asyncio.Event()
            async def wait():
                await exited.wait()
                return process.returncode
            def kill():
                process.returncode = -9
                exited.set()
            process.wait = wait
            process.kill = Mock(side_effect=kill)
            create.side_effect = None
            create.return_value = process
            check.side_effect = [None, None, RuntimeError("Stopped")]
            with self.assertRaisesRegex(RuntimeError, "Stopped"):
                await load_coreference(uuid.uuid4(), documents, check)
            process.kill.assert_called_once()
        outputs = [run["outputs"] for run in trace_client.updated]
        self.assertEqual([item["cache_hit"] for item in outputs if item["outcome"] == "ready"], [False, True, False])
        self.assertEqual(outputs[-1], {"outcome": "not_completed", "error_type": "RuntimeError"})
        self.assertNotIn(text, json.dumps(trace_client.created + trace_client.updated, default=str))
