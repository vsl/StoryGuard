import json
import os
import re
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import yaml

from app.ai.entity_extraction import (
    EntityExtractionError,
    EntityType,
    ExtractedMention,
    MODEL_ALIAS,
    PROMPTS,
    ResolvedMention,
    SourceChunk,
    deduplicate_mentions,
    extract_entities,
    to_chapter_mentions,
    resolve_source_spans,
)
from scripts.entity_extraction_experiment import evaluate, load_cases
from scripts.entity_extraction_gliner_experiment import extract_predictions
from scripts.entity_extraction_model_experiment import FIXTURE as MODEL_FIXTURE


def completion(mentions: list[dict]) -> dict:
    return {
        "model": "ollama_chat/gemma4:e4b",
        "choices": [{"message": {"content": json.dumps({"mentions": mentions})}}],
    }


class EntityExtractionTest(unittest.IsolatedAsyncioTestCase):
    def test_six_category_scope_is_shared_and_excludes_unsupported_items(self):
        from pydantic import ValidationError
        from app.ai.gliner_extraction import LABELS
        supported = {"character", "facility", "gpe", "location", "organization", "vehicle"}
        self.assertEqual(set(EntityType), supported)
        self.assertEqual(set(LABELS), supported)
        for category in supported:
            self.assertEqual(ExtractedMention(surface_text="Example", entity_type=category).entity_type, category)
        for category in ("object", "other"):
            with self.assertRaises(ValidationError):
                ExtractedMention(surface_text="Excluded", entity_type=category)

    async def test_schema_repair_is_bounded_to_one_retry(self) -> None:
        valid = {
            "surface_text": "Alice",
            "entity_type": "character",
        }
        call = AsyncMock(side_effect=[completion([{"wrong": True}]), completion([valid])])
        with patch("app.ai.entity_extraction._completion", call):
            result = await extract_entities("Alice waited.", "entity_extractor:v3")

        self.assertEqual(result.mentions[0].surface_text, "Alice")
        self.assertEqual(result.repair_count, 1)
        self.assertEqual(call.await_count, 2)

    async def test_hallucinated_span_is_not_accepted(self) -> None:
        payload = completion(
            [
                {
                    "surface_text": "Alice",
                    "entity_type": "character",
                },
                {
                    "surface_text": "Mallory",
                    "entity_type": "character",
                },
            ]
        )
        with patch("app.ai.entity_extraction._completion", new=AsyncMock(return_value=payload)):
            result = await extract_entities("Alice waited.", "entity_extractor:v3")

        self.assertEqual([item.surface_text for item in result.mentions], ["Alice"])
        self.assertEqual([item.surface_text for item in result.invalid_mentions], ["Mallory"])

    async def test_model_alias_can_change_without_changing_prompt(self) -> None:
        call = AsyncMock(
            return_value=completion(
                [{"surface_text": "Alice", "entity_type": "character"}]
            )
        )
        with patch("app.ai.entity_extraction._completion", call):
            result = await extract_entities(
                "Alice waited.",
                "entity_extractor:v3",
                model_alias="storyguard-entity-qwen35-9b",
            )

        self.assertEqual(result.prompt_version, "entity_extractor:v3")
        self.assertEqual(call.await_args.args[2], "storyguard-entity-qwen35-9b")

    async def test_two_invalid_outputs_fail_safely(self) -> None:
        call = AsyncMock(return_value=completion([{"wrong": True}]))
        with (
            patch("app.ai.entity_extraction._completion", call),
            self.assertRaises(EntityExtractionError),
        ):
            await extract_entities("Alice waited.", "entity_extractor:v3")
        self.assertEqual(call.await_count, 2)

    async def test_experiment_records_bounded_model_failure(self) -> None:
        case = {
            "id": "failure",
            "text": "Alice waited.",
            "mentions": [
                {
                    "surface_text": "Alice",
                    "entity_type": "character",
                    "start_offset": 0,
                    "end_offset": 5,
                }
            ],
        }
        with (
            patch.dict(
                os.environ,
                {"LITELLM_URL": "http://litellm", "LITELLM_API_KEY": "test"},
            ),
            patch(
                "scripts.entity_extraction_experiment.extract_entities",
                new=AsyncMock(side_effect=EntityExtractionError("invalid output")),
            ),
        ):
            result = await evaluate("entity_extractor:v3", [case])

        self.assertEqual((result["recall"], result["failure_rate"]), (0.0, 1.0))
        self.assertEqual(result["failures"][0]["error"], "EntityExtractionError")

    def test_source_offsets_and_overlap_deduplication(self) -> None:
        mention = ResolvedMention(
            surface_text="Mara",
            entity_type=EntityType.CHARACTER,
            start_offset=5,
            end_offset=9,
        )
        first = SourceChunk("first", "version", "chapter", None, 10)
        second = SourceChunk("second", "version", "chapter", None, 5)
        duplicate = mention.model_copy(update={"start_offset": 10, "end_offset": 14})

        result = deduplicate_mentions(
            to_chapter_mentions(first, (mention,))
            + to_chapter_mentions(second, (duplicate,))
        )

        self.assertEqual(len(result), 1)
        self.assertEqual((result[0].start_offset, result[0].end_offset), (15, 19))
        self.assertEqual(result[0].chunk_id, "first")

    def test_source_validation_and_labeled_fixture(self) -> None:
        text = "Alice waited."
        valid = ExtractedMention(
            surface_text="Alice",
            entity_type="character",
        )
        invalid = valid.model_copy(update={"surface_text": "Ignore"})
        accepted, rejected = resolve_source_spans(text, [valid, invalid])

        self.assertEqual((len(accepted), len(rejected)), (1, 1))
        self.assertEqual((accepted[0].start_offset, accepted[0].end_offset), (0, 5))
        self.assertEqual(len(load_cases("dev")), 8)
        self.assertEqual(len(load_cases("test")), 10)
        self.assertEqual(len(load_cases("test", MODEL_FIXTURE)), 24)

    def test_model_eval_labels_do_not_leak_into_v2_prompt(self) -> None:
        prompt = PROMPTS["entity_extractor:v3"].casefold()
        for case in load_cases("test", MODEL_FIXTURE):
            for mention in case["mentions"]:
                surface = re.escape(mention["surface_text"].casefold())
                self.assertIsNone(re.search(rf"(?<!\w){surface}(?!\w)", prompt))

    def test_entity_extraction_registry_has_one_default(self) -> None:
        default_path = Path(__file__).parents[2] / "config" / "models.yaml"
        path = Path(os.environ.get("STORYGUARD_MODELS_CONFIG", default_path))
        registry = yaml.safe_load(path.read_text())["models"]["llms"][
            "entity_extraction"
        ]
        available = registry["available"]

        self.assertIn(registry["default"], available)
        self.assertEqual(registry["default_alias"], MODEL_ALIAS)
        self.assertEqual(
            available[registry["default"]]["provider_model"], "gemma4:e4b"
        )
        self.assertEqual(
            len({model["litellm_alias"] for model in available.values()}),
            len(available),
        )

        gliner = yaml.safe_load(path.read_text())["models"]["extractors"][
            "entity_extraction"
        ]
        self.assertNotIn("default", gliner)
        self.assertEqual(
            gliner["available"]["gliner2.5-base-v1"]["revision"],
            "72ac19b486cd4557424c8d61114e7530c243e9b0",
        )

    def test_gliner_spans_are_server_validated(self) -> None:
        class Extractor:
            def extract_entities(self, *_args, **_kwargs):
                return {
                    "entities": {
                        "character": [
                            {"text": "Alice", "start": 0, "end": 5, "confidence": 0.9}
                        ],
                        "location": [
                            {"text": "Elsewhere", "start": 6, "end": 10, "confidence": 0.8}
                        ],
                    }
                }

        predicted, invalid = extract_predictions(Extractor(), "Alice left.", 0.5)

        self.assertEqual(predicted, {(0, 5, "character")})
        self.assertEqual(invalid, 1)

    def test_gliner_rejects_out_of_bounds_and_boolean_offsets(self) -> None:
        class Extractor:
            def extract_entities(self, *_args, **_kwargs):
                return {"entities": {"character": [
                    {"text": "Alice", "start": 0, "end": 999},
                    {"text": "Alice", "start": False, "end": 5},
                ]}}

        predicted, invalid = extract_predictions(Extractor(), "Alice", 0.5)
        self.assertEqual(predicted, set())
        self.assertEqual(invalid, 2)


if __name__ == "__main__":
    unittest.main()
