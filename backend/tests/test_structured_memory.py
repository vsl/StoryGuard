import json
import os
import unittest
import uuid
from unittest.mock import AsyncMock, patch

from app.ai.structured_memory import (
    CANDIDATE_PROMPT_VERSION,
    CANDIDATE_V2_PROMPT_VERSION,
    CANDIDATE_V3_PROMPT_VERSION,
    CANDIDATE_V4_PROMPT_VERSION,
    CANDIDATE_V5_PROMPT_VERSION,
    CANDIDATE_V6_PROMPT_VERSION,
    CANDIDATE_V7_PROMPT_VERSION,
    PROMPT_VERSION,
    PROMPTS,
    EntityRef,
    EvidenceBlock,
    ExtractedMemory,
    ExtractionInput,
    chunk_evidence,
    extract_structured_memory,
    validate_memory,
)
from scripts.structured_memory_experiment import FIXTURES, _semantic_sets, _sets, load_cases, summarize


def completion(output: dict) -> dict:
    return {
        "model": "ollama_chat/gemma4:e4b",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "choices": [{"message": {"content": json.dumps(output)}}],
    }


class StructuredMemoryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        text = "Mara and Ilya divorced."
        self.inputs = ExtractionInput(
            evidence=[EvidenceBlock(id="e1", text=text, start_offset=0, end_offset=len(text))],
            entities=[
                EntityRef(id="mara", name="Mara", type="character"),
                EntityRef(id="ilya", name="Ilya", type="character"),
            ],
        )

    def test_server_evidence_id_is_deterministic_and_bound_to_source(self) -> None:
        version_id = str(uuid.uuid4())
        first = chunk_evidence("Mara waited.", version_id, "chapter", "chunk", 10)
        same = chunk_evidence("Mara waited.", version_id, "chapter", "chunk", 10)
        changed = chunk_evidence("Mara left.", version_id, "chapter", "chunk", 10)

        self.assertEqual(first, same)
        self.assertNotEqual(first.id, changed.id)
        self.assertEqual((first.start_offset, first.end_offset), (10, 22))

    def test_extraction_input_rejects_ambiguous_server_ids_and_offsets(self) -> None:
        with self.assertRaises(ValueError):
            EvidenceBlock(id="e1", text="Mara", start_offset=0, end_offset=5)
        with self.assertRaises(ValueError):
            ExtractionInput(evidence=[self.inputs.evidence[0], self.inputs.evidence[0]])
        with self.assertRaises(ValueError):
            ExtractionInput(
                evidence=self.inputs.evidence,
                entities=[self.inputs.entities[0], self.inputs.entities[0]],
            )
        with self.assertRaises(ValueError):
            ExtractedMemory.model_validate({
                "facts": [], "relationships": [],
                "events": [{
                    "local_id": "arrival", "event_type": "movement",
                    "description": "Mara arrived", "chronological_time_normalized": "2024-03",
                    "evidence_ids": ["e1"],
                }],
            })
        with self.assertRaises(ValueError):
            ExtractedMemory.model_validate({
                "facts": [], "events": [],
                "relationships": [{
                    "source_text": "Mara", "relation_type": "spouse_of",
                    "target_text": "Ilya", "change": "ended", "event_local_id": "",
                    "evidence_ids": ["e1"],
                }],
            })

    def test_candidate_rejects_invented_ids_and_missing_entity_links(self) -> None:
        output = ExtractedMemory.model_validate({
            "facts": [{
                "subject_text": "Mara", "predicate": "status", "object_text": "divorced",
                "fact_type": "attribute", "evidence_ids": ["invented"],
            }],
            "events": [],
            "relationships": [{
                "source_text": "Mara", "relation_type": "spouse_of", "target_text": "Ilya",
                "change": "asserted", "evidence_ids": ["e1"],
            }],
        })

        validated = validate_memory(output, self.inputs, require_entity_ids=True)

        self.assertEqual(validated.accepted_count, 0)
        self.assertEqual(set(validated.rejection_reasons), {
            "fact:invalid_evidence_id", "relationship:missing_entity_id",
        })

    def test_baseline_resolves_unique_names_but_keeps_literals_unlinked(self) -> None:
        output = ExtractedMemory.model_validate({
            "facts": [{
                "subject_text": "Mara", "predicate": "eye_color", "object_text": "green",
                "fact_type": "attribute", "evidence_ids": ["e1"],
            }],
            "events": [], "relationships": [],
        })

        validated = validate_memory(output, self.inputs, require_entity_ids=False)

        self.assertEqual(validated.facts[0].subject_entity_id, "mara")
        self.assertIsNone(validated.facts[0].object_entity_id)

    def test_server_rejects_unmatched_model_links_and_drops_extra_event_links(self) -> None:
        output = ExtractedMemory.model_validate({
            "facts": [{
                "subject_text": "Mallory", "subject_entity_id": "mara", "predicate": "status",
                "object_text": "ready", "fact_type": "state", "evidence_ids": ["e1"],
            }],
            "events": [{
                "local_id": "discovery", "event_type": "discovery", "description": "Mara noticed it",
                "participant_texts": ["Mara"], "participant_entity_ids": ["mara", "ilya"],
                "evidence_ids": ["e1"],
            }],
            "relationships": [{
                "source_text": "Mallory", "source_entity_id": "mara", "relation_type": "friend_of",
                "target_text": "Ilya", "target_entity_id": "ilya", "evidence_ids": ["e1"],
            }],
        })

        validated = validate_memory(
            output, self.inputs, require_entity_ids=False, controlled_taxonomy=True,
        )

        self.assertEqual(validated.facts, ())
        self.assertEqual(validated.events[0].participant_entity_ids, ["mara"])
        self.assertEqual(validated.relationships, ())
        self.assertEqual(validated.rejection_reasons, (
            "fact:entity_text_mismatch", "relationship:entity_text_mismatch",
        ))
        strict = validate_memory(
            output.model_copy(update={"facts": [], "relationships": []}),
            self.inputs, require_entity_ids=True, controlled_taxonomy=True,
        )
        self.assertEqual(strict.events, ())
        self.assertEqual(strict.rejection_reasons, ("event:entity_text_mismatch",))

    def test_relationship_end_must_reference_an_accepted_event(self) -> None:
        output = ExtractedMemory.model_validate({
            "facts": [],
            "events": [{
                "local_id": "divorce", "event_type": "relationship_ended",
                "description": "Mara and Ilya divorced", "participant_texts": ["Mara", "Ilya"],
                "participant_entity_ids": ["mara", "ilya"], "evidence_ids": ["e1"],
            }],
            "relationships": [{
                "source_text": "Mara", "source_entity_id": "mara", "relation_type": "spouse_of",
                "target_text": "Ilya", "target_entity_id": "ilya", "change": "ended",
                "event_local_id": "divorce", "evidence_ids": ["e1"],
            }],
        })

        validated = validate_memory(output, self.inputs, require_entity_ids=True)

        self.assertEqual((len(validated.events), len(validated.relationships)), (1, 1))
        self.assertEqual(validated.relationships[0].event_local_id, "divorce")

    def test_relationship_change_event_must_share_people_and_evidence(self) -> None:
        other = "Ilya left."
        inputs = self.inputs.model_copy(update={"evidence": [
            *self.inputs.evidence,
            EvidenceBlock(id="e2", text=other, start_offset=0, end_offset=len(other)),
        ]})
        base = {
            "facts": [],
            "events": [{
                "local_id": "divorce", "event_type": "relationship_ended",
                "description": "Mara divorced", "participant_texts": ["Mara"],
                "evidence_ids": ["e1"],
            }],
            "relationships": [{
                "source_text": "Mara", "relation_type": "spouse_of", "target_text": "Ilya",
                "change": "ended", "event_local_id": "divorce", "evidence_ids": ["e1"],
            }],
        }
        missing_person = validate_memory(
            ExtractedMemory.model_validate(base), inputs,
            require_entity_ids=False, controlled_taxonomy=True,
        )
        no_shared_evidence = validate_memory(
            ExtractedMemory.model_validate({
                **base,
                "events": [{**base["events"][0], "participant_texts": ["Mara", "Ilya"]}],
                "relationships": [{**base["relationships"][0], "evidence_ids": ["e2"]}],
            }),
            inputs, require_entity_ids=False, controlled_taxonomy=True,
        )

        self.assertEqual(missing_person.rejection_reasons, (
            "relationship:relationship_event_entities_mismatch",
        ))
        self.assertEqual(no_shared_evidence.rejection_reasons, (
            "relationship:relationship_event_evidence_mismatch",
        ))

    def test_v2_enforces_taxonomy_event_pairing_and_symmetric_order(self) -> None:
        output = ExtractedMemory.model_validate({
            "facts": [{
                "subject_text": "Mara", "subject_entity_id": "mara", "predicate": "has_status",
                "object_text": "ready", "fact_type": "attribute", "evidence_ids": ["e1"],
            }],
            "events": [{
                "local_id": "divorce", "event_type": "relationship_started",
                "description": "Mara and Ilya divorced", "participant_texts": ["Mara", "Ilya"],
                "participant_entity_ids": ["mara", "ilya"], "evidence_ids": ["e1"],
            }],
            "relationships": [{
                "source_text": "Mara", "source_entity_id": "mara", "relation_type": "spouse_of",
                "target_text": "Ilya", "target_entity_id": "ilya", "change": "ended",
                "event_local_id": "divorce", "evidence_ids": ["e1"],
            }, {
                "source_text": "Mara", "source_entity_id": "mara", "relation_type": "sibling_of",
                "target_text": "Ilya", "target_entity_id": "ilya", "change": "asserted",
                "evidence_ids": ["e1"],
            }],
        })

        validated = validate_memory(
            output, self.inputs, require_entity_ids=True, controlled_taxonomy=True,
        )

        self.assertEqual(validated.rejection_reasons, (
            "fact:invalid_fact_taxonomy", "relationship:relationship_event_mismatch",
        ))
        self.assertEqual(
            (validated.relationships[0].source_entity_id, validated.relationships[0].target_entity_id),
            ("ilya", "mara"),
        )

    async def test_invalid_first_result_gets_one_repair(self) -> None:
        invalid = {
            "facts": [{
                "subject_text": "Mara", "subject_entity_id": "mallory", "predicate": "status",
                "object_text": "divorced", "fact_type": "attribute", "evidence_ids": ["e1"],
            }], "events": [], "relationships": [],
        }
        valid = {
            "facts": [{
                "subject_text": "Mara", "subject_entity_id": "mara", "predicate": "status",
                "object_text": "divorced", "fact_type": "attribute", "evidence_ids": ["e1"],
            }], "events": [], "relationships": [],
        }
        call = AsyncMock(side_effect=[completion(invalid), completion(valid)])
        with patch("app.ai.structured_memory._completion", call):
            result = await extract_structured_memory(self.inputs, CANDIDATE_PROMPT_VERSION)

        self.assertEqual(result.repair_count, 1)
        self.assertEqual(result.memory.facts[0].subject_entity_id, "mara")
        self.assertEqual(result.usage["total_tokens"], 30)
        self.assertEqual(call.await_count, 2)

    async def test_v2_repairs_disallowed_taxonomy(self) -> None:
        invalid = {
            "facts": [{
                "subject_text": "Mara", "subject_entity_id": "mara", "predicate": "has_status",
                "object_text": "ready", "fact_type": "attribute", "evidence_ids": ["e1"],
            }], "events": [], "relationships": [],
        }
        valid = {
            "facts": [{
                "subject_text": "Mara", "subject_entity_id": "mara", "predicate": "status",
                "object_text": "ready", "fact_type": "state", "evidence_ids": ["e1"],
            }], "events": [], "relationships": [],
        }
        call = AsyncMock(side_effect=[completion(invalid), completion(valid)])
        with patch("app.ai.structured_memory._completion", call):
            result = await extract_structured_memory(self.inputs, CANDIDATE_V2_PROMPT_VERSION)

        self.assertEqual(result.repair_count, 1)
        self.assertEqual(result.memory.facts[0].predicate, "status")
        self.assertEqual(call.await_count, 2)

    async def test_v3_server_links_unique_names_without_model_ids(self) -> None:
        output = {
            "facts": [],
            "events": [{
                "local_id": "divorce", "event_type": "relationship_ended",
                "description": "Mara and Ilya divorced", "participant_texts": ["Mara", "Ilya"],
                "evidence_ids": ["e1"],
            }],
            "relationships": [{
                "source_text": "Mara", "relation_type": "spouse_of", "target_text": "Ilya",
                "change": "ended", "event_local_id": "divorce", "evidence_ids": ["e1"],
            }],
        }
        with patch(
            "app.ai.structured_memory._completion", AsyncMock(return_value=completion(output)),
        ):
            result = await extract_structured_memory(self.inputs, CANDIDATE_V3_PROMPT_VERSION)

        self.assertEqual(result.memory.events[0].participant_entity_ids, ["ilya", "mara"])
        self.assertEqual(
            (result.memory.relationships[0].source_entity_id,
             result.memory.relationships[0].target_entity_id),
            ("ilya", "mara"),
        )

    def test_v3_does_not_guess_ambiguous_alias(self) -> None:
        inputs = self.inputs.model_copy(update={"entities": [
            *self.inputs.entities,
            EntityRef(id="malia", name="Malia", type="character", aliases=["M"]),
            EntityRef(id="marin", name="Marin", type="character", aliases=["M"]),
        ]})
        output = ExtractedMemory.model_validate({
            "facts": [], "events": [],
            "relationships": [{
                "source_text": "M", "relation_type": "friend_of", "target_text": "Ilya",
                "change": "asserted", "evidence_ids": ["e1"],
            }],
        })

        validated = validate_memory(
            output, inputs, require_entity_ids=False, controlled_taxonomy=True,
        )

        self.assertEqual(validated.relationships, ())
        self.assertEqual(
            validated.rejection_reasons, ("relationship:unresolved_relationship_endpoint",),
        )

    async def test_v5_keeps_v3_prompt_and_canonicalizes_confirmed_event_roles(self) -> None:
        self.assertEqual(PROMPTS[CANDIDATE_V5_PROMPT_VERSION], PROMPTS[CANDIDATE_V3_PROMPT_VERSION])
        visit = "In summer 2018, Daniel visited Paris."
        crash = "At dawn, the Aurora Express derailed near North Ridge."
        inputs = ExtractionInput(
            evidence=[
                EvidenceBlock(id="e1", text=visit, start_offset=0, end_offset=len(visit)),
                EvidenceBlock(id="e2", text=crash, start_offset=0, end_offset=len(crash)),
            ],
            entities=[
                EntityRef(id="daniel", name="Daniel", type="character"),
                EntityRef(id="paris", name="Paris", type="gpe"),
                EntityRef(id="train", name="Aurora Express", type="vehicle"),
                EntityRef(id="ridge", name="North Ridge", type="location"),
            ],
        )
        output = {
            "facts": [], "relationships": [],
            "events": [{
                "local_id": "visit", "event_type": "movement",
                "description": "Daniel visited Paris", "participant_texts": ["Daniel", "Paris"],
                "chronological_time_raw": "In summer 2018", "evidence_ids": ["e1"],
            }, {
                "local_id": "crash", "event_type": "accident",
                "description": "Aurora Express derailed near North Ridge",
                "location_texts": ["North Ridge"], "chronological_time_raw": "At dawn",
                "evidence_ids": ["e2"],
            }],
        }
        with patch(
            "app.ai.structured_memory._completion", AsyncMock(return_value=completion(output)),
        ):
            result = await extract_structured_memory(inputs, CANDIDATE_V5_PROMPT_VERSION)

        self.assertEqual(result.memory.events[0].participant_entity_ids, ["daniel"])
        self.assertEqual(result.memory.events[0].location_entity_ids, ["paris"])
        self.assertEqual(result.memory.events[0].participant_texts, ["Daniel"])
        self.assertEqual(result.memory.events[0].location_texts, ["Paris"])
        self.assertEqual(result.memory.events[1].participant_entity_ids, ["train"])
        self.assertEqual(result.memory.events[1].location_entity_ids, ["ridge"])

    async def test_v6_does_not_enrich_ambiguous_communication_roles(self) -> None:
        self.assertEqual(PROMPTS[CANDIDATE_V6_PROMPT_VERSION], PROMPTS[CANDIDATE_V3_PROMPT_VERSION])
        output = {
            "facts": [], "relationships": [],
            "events": [{
                "local_id": "note", "event_type": "communication",
                "description": "Mara read a note about Ilya", "participant_texts": ["Mara"],
                "evidence_ids": ["e1"],
            }],
        }
        with patch(
            "app.ai.structured_memory._completion", AsyncMock(return_value=completion(output)),
        ):
            result = await extract_structured_memory(self.inputs, CANDIDATE_V6_PROMPT_VERSION)

        self.assertEqual(result.memory.events[0].participant_entity_ids, ["mara"])

    async def test_v7_repairs_then_removes_weak_communication(self) -> None:
        self.assertEqual(PROMPT_VERSION, CANDIDATE_V7_PROMPT_VERSION)
        self.assertEqual(PROMPTS[CANDIDATE_V7_PROMPT_VERSION], PROMPTS[CANDIDATE_V3_PROMPT_VERSION])
        output = {
            "facts": [], "relationships": [],
            "events": [{
                "local_id": "note", "event_type": "communication",
                "description": "Mara read a note about Ilya", "participant_texts": ["Mara"],
                "evidence_ids": ["e1"],
            }],
        }
        call = AsyncMock(side_effect=[completion(output), completion(output)])
        with patch("app.ai.structured_memory._completion", call):
            result = await extract_structured_memory(self.inputs, CANDIDATE_V7_PROMPT_VERSION)

        self.assertEqual(result.memory.events, ())
        self.assertEqual(
            result.memory.rejection_reasons, ("event:insufficient_communication_participants",),
        )
        self.assertEqual(result.repair_count, 1)

    async def test_v7_accepts_two_explicit_communication_participants(self) -> None:
        output = {
            "facts": [], "relationships": [],
            "events": [{
                "local_id": "warning", "event_type": "communication",
                "description": "Mara warned Ilya", "participant_texts": ["Mara", "Ilya"],
                "evidence_ids": ["e1"],
            }],
        }
        with patch(
            "app.ai.structured_memory._completion", AsyncMock(return_value=completion(output)),
        ):
            result = await extract_structured_memory(self.inputs, CANDIDATE_V7_PROMPT_VERSION)

        self.assertEqual(result.memory.events[0].participant_entity_ids, ["ilya", "mara"])

    async def test_v7_does_not_count_a_place_as_a_communication_participant(self) -> None:
        inputs = self.inputs.model_copy(update={"entities": [
            self.inputs.entities[0],
            self.inputs.entities[1].model_copy(update={"type": "gpe"}),
        ]})
        output = {
            "facts": [], "relationships": [],
            "events": [{
                "local_id": "broadcast", "event_type": "communication",
                "description": "Mara broadcast from Ilya", "participant_texts": ["Mara", "Ilya"],
                "evidence_ids": ["e1"],
            }],
        }
        call = AsyncMock(side_effect=[completion(output), completion(output)])
        with patch("app.ai.structured_memory._completion", call):
            result = await extract_structured_memory(inputs, CANDIDATE_V7_PROMPT_VERSION)

        self.assertEqual(result.memory.events, ())
        self.assertEqual(
            result.memory.rejection_reasons, ("event:insufficient_communication_participants",),
        )

    def test_frozen_fixture_and_metric_shape(self) -> None:
        cases = load_cases("test")
        self.assertEqual(len(cases), 10)
        self.assertEqual(len(load_cases("test", FIXTURES["v1"])), 10)
        self.assertEqual(len(load_cases("test", FIXTURES["v3"])), 12)
        row = {
            "id": cases[0]["id"],
            "expected": {key: sorted(value) for key, value in _sets(cases[0]["expected_output"]).items()},
            "predicted": {key: [] for key in ("facts", "events", "relationships")},
            "semantic_expected": {
                key: sorted(value) for key, value in _semantic_sets(cases[0]["expected_output"]).items()
            },
            "semantic_predicted": {key: [] for key in ("facts", "events", "relationships")},
            "expected_links": [], "predicted_links": [], "raw_count": 0,
            "rejected_count": 0, "rejection_reasons": [], "repair_count": 0,
            "usage": {}, "latency_ms": 1.0, "error": None,
        }
        metrics = summarize([row])
        self.assertIn("macro_f1", metrics)
        self.assertIn("semantic_macro_f1", metrics)
        self.assertEqual(metrics["accepted_evidence_validity"], 1.0)

        expected = cases[4]["expected_output"]
        predicted = expected.model_copy(update={
            "events": [expected.events[0].model_copy(update={
                "chronological_time_raw": "In March 2024",
            })],
        })
        self.assertNotEqual(_sets(expected)["events"], _sets(predicted)["events"])
        self.assertEqual(_semantic_sets(expected)["events"], _semantic_sets(predicted)["events"])

        fact_expected = cases[0]["expected_output"]
        wrong_predicate = fact_expected.model_copy(update={
            "facts": [fact_expected.facts[0].model_copy(update={"predicate": "occupation"})],
        })
        self.assertNotEqual(
            _semantic_sets(fact_expected)["facts"],
            _semantic_sets(wrong_predicate)["facts"],
        )


if __name__ == "__main__":
    unittest.main()
