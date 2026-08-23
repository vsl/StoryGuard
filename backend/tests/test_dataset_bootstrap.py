import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.bootstrap_datasets import bootstrap


class DatasetBootstrapTest(unittest.TestCase):
    def test_is_reproducible_and_fails_closed_on_source_drift(self) -> None:
        rows = {
            ("books", "default"): [
                {
                    "id": "11",
                    "text": "Alice was beginning to get very tired.",
                    "metadata": {
                        "license": "Public Domain",
                        "title": "Alice's Adventures in Wonderland",
                        "url": "https://example.test/11",
                    },
                }
            ],
            ("qa", "default"): [
                {"context": "ignored", "question": "ignored", "response": "ignored"},
                {"context": "Story", "question": "Who?", "response": "Alice"},
            ],
            ("retrieval", "queries"): [
                {"query": "Where?", "answer": "Wonderland", "chunk_id": "c1"}
            ],
            ("retrieval", "documents"): [{"chunk_id": "c1", "chunk": "Down the hole."}],
        }
        calls = []

        def loader(hf_id, config, **kwargs):
            calls.append((hf_id, config, kwargs))
            return iter(rows[(hf_id, config)])

        registry = {
            "registry_version": 1,
            "transform_version": "test-v1",
            "fixtures_dir": "data/fixtures",
            "manifest_path": "data/manifest.json",
            "datasets": {
                "public_domain_manuscripts": {
                    "hf_id": "books", "revision": "a" * 40, "config": "default",
                    "split": "train", "selected_ids": ["11"], "fixture": "books.jsonl",
                    "provenance_url": "https://example.test/books", "license_notes": "PD",
                },
                "story_qa": {
                    "hf_id": "qa", "revision": "b" * 40, "config": "default",
                    "split": "train", "selected_rows": [1], "fixture": "qa.jsonl",
                    "provenance_url": "https://example.test/qa", "license_notes": "local",
                },
                "retrieval_eval": {
                    "hf_id": "retrieval", "revision": "c" * 40,
                    "query_config": "queries", "document_config": "documents",
                    "split": "test", "selected_query_rows": [0],
                    "query_fixture": "queries.jsonl", "document_fixture": "documents.jsonl",
                    "provenance_url": "https://example.test/retrieval", "license_notes": "local",
                },
            },
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "datasets.yaml"
            config.write_text(yaml.safe_dump(registry))

            first = bootstrap(config, root, loader)
            second = bootstrap(config, root, loader)
            self.assertEqual(first, second)
            self.assertTrue(all(call[2]["streaming"] for call in calls))
            self.assertTrue(all(len(call[2]["revision"]) == 40 for call in calls))
            self.assertEqual(calls[0][2]["filters"], [("id", "in", ["11"])])

            fixture = root / "data/fixtures/books.jsonl"
            original = fixture.read_bytes()
            rows[("books", "default")][0]["text"] = "changed"
            with self.assertRaisesRegex(RuntimeError, "committed manifest"):
                bootstrap(config, root, loader)
            self.assertEqual(fixture.read_bytes(), original)

            manifest = json.loads((root / "data/manifest.json").read_text())
            self.assertEqual(manifest["datasets"]["story_qa"]["fixture"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
