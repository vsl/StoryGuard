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
            ("retrieval", "questions"): [
                {
                    "title": "Wonderland",
                    "question": "Where?",
                    "answer": "Wonderland",
                    "chunk-must-contain": "Down the hole.",
                }
            ],
            ("retrieval", "corpus"): [
                {
                    "author": "Lewis Carroll",
                    "date": "1865",
                    "title": "Wonderland",
                    "text": "Down the hole.",
                }
            ],
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
                    "query_config": "questions", "document_config": "corpus",
                    "split": "train", "selected_titles": ["Wonderland"],
                    "development_titles": ["Wonderland"], "expected_query_count": 1,
                    "query_fixture": "queries.jsonl", "document_fixture": "documents.jsonl",
                    "provenance_url": "https://example.test/retrieval", "license_notes": "local",
                    "original_source": {"hf_id": "original", "revision": "d" * 40},
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
            query = json.loads((root / "data/fixtures/queries.jsonl").read_text())
            self.assertEqual(query["evidence"], "Down the hole.")
            self.assertEqual(query["split"], "dev")

    def test_rejects_non_unique_evidence(self) -> None:
        rows = {
            ("books", "default"): [{
                "id": "11", "text": "Book", "metadata": {
                    "license": "Public Domain", "title": "Book", "url": "https://books/11"
                }
            }],
            ("qa", "default"): [{"context": "C", "question": "Q", "response": "A"}],
            ("retrieval", "corpus"): [{
                "author": "A", "date": "1900", "title": "Book", "text": "same same"
            }],
            ("retrieval", "questions"): [{
                "title": "Book", "question": "Q", "answer": "A",
                "chunk-must-contain": "same",
            }],
        }

        def loader(hf_id, config, **kwargs):
            return iter(rows[(hf_id, config)])

        registry = {
            "registry_version": 1, "transform_version": "test-v1",
            "fixtures_dir": "fixtures", "manifest_path": "manifest.json",
            "datasets": {
                "public_domain_manuscripts": {
                    "hf_id": "books", "revision": "a" * 40, "config": "default",
                    "split": "train", "selected_ids": ["11"], "fixture": "books.jsonl",
                    "provenance_url": "https://books", "license_notes": "PD",
                },
                "story_qa": {
                    "hf_id": "qa", "revision": "b" * 40, "config": "default",
                    "split": "train", "selected_rows": [0], "fixture": "qa.jsonl",
                    "provenance_url": "https://qa", "license_notes": "local",
                },
                "retrieval_eval": {
                    "hf_id": "retrieval", "revision": "c" * 40,
                    "query_config": "questions", "document_config": "corpus",
                    "split": "train", "selected_titles": ["Book"],
                    "development_titles": [], "expected_query_count": 1,
                    "query_fixture": "queries.jsonl", "document_fixture": "documents.jsonl",
                    "provenance_url": "https://retrieval", "license_notes": "local",
                    "original_source": {"hf_id": "original", "revision": "d" * 40},
                },
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "datasets.yaml"
            config.write_text(yaml.safe_dump(registry))
            with self.assertRaisesRegex(ValueError, "one exact evidence occurrence"):
                bootstrap(config, root, loader)


if __name__ == "__main__":
    unittest.main()
