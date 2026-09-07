"""Frozen baseline-vs-grounded structured-memory diagnostic."""

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import time
import uuid
from pathlib import Path

import httpx

from app.ai.entity_resolution import normalize_name
from app.ai.structured_memory import (
    BASELINE_PROMPT_VERSION,
    CANDIDATE_PROMPT_VERSION,
    CANDIDATE_V2_PROMPT_VERSION,
    CANDIDATE_V3_PROMPT_VERSION,
    CANDIDATE_V4_PROMPT_VERSION,
    CANDIDATE_V5_PROMPT_VERSION,
    CANDIDATE_V6_PROMPT_VERSION,
    CANDIDATE_V7_PROMPT_VERSION,
    PROMPTS,
    EntityRef,
    EvidenceBlock,
    ExtractedMemory,
    ExtractionInput,
    StructuredMemoryError,
    ValidatedMemory,
    extract_structured_memory,
    validate_memory,
)


ROOT = Path(__file__).parents[2]
IMPLEMENTATION = ROOT / "backend/app/ai/structured_memory.py"
FIXTURES = {
    "v1": ROOT / "data/datasets/fixtures/structured_memory_v1.jsonl",
    "v2": ROOT / "data/datasets/fixtures/structured_memory_v2.jsonl",
    "v3": ROOT / "data/datasets/fixtures/structured_memory_v3.jsonl",
}
EXPERIMENTS = {
    "v1": (FIXTURES["v1"], BASELINE_PROMPT_VERSION, CANDIDATE_PROMPT_VERSION),
    "v2": (FIXTURES["v2"], BASELINE_PROMPT_VERSION, CANDIDATE_V2_PROMPT_VERSION),
    "v3": (FIXTURES["v2"], CANDIDATE_V2_PROMPT_VERSION, CANDIDATE_V3_PROMPT_VERSION),
    "v4": (FIXTURES["v2"], CANDIDATE_V3_PROMPT_VERSION, CANDIDATE_V4_PROMPT_VERSION),
    "v5": (FIXTURES["v2"], CANDIDATE_V3_PROMPT_VERSION, CANDIDATE_V5_PROMPT_VERSION),
    "v6": (FIXTURES["v2"], CANDIDATE_V5_PROMPT_VERSION, CANDIDATE_V6_PROMPT_VERSION),
    "v7": (FIXTURES["v3"], CANDIDATE_V6_PROMPT_VERSION, CANDIDATE_V7_PROMPT_VERSION),
}


def load_cases(split: str, fixture: Path = FIXTURES["v2"]) -> list[dict]:
    cases = [json.loads(line) for line in fixture.read_text().splitlines() if line.strip()]
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Structured-memory case IDs must be unique")
    selected = [case for case in cases if case["split"] == split]
    if not selected:
        raise ValueError("Structured-memory split is empty")
    for case in selected:
        evidence = [
            EvidenceBlock(
                id=item["id"], text=item["text"], start_offset=0,
                end_offset=len(item["text"]),
            )
            for item in case["evidence"]
        ]
        inputs = ExtractionInput(evidence=evidence, entities=[EntityRef(**item) for item in case["entities"]])
        expected = ExtractedMemory.model_validate(case["expected"])
        validated = validate_memory(
            expected, inputs, require_entity_ids=False,
            controlled_taxonomy=fixture in {FIXTURES["v2"], FIXTURES["v3"]},
        )
        if validated.rejected_count:
            raise ValueError(
                f"Invalid expected output in {case['id']}: {','.join(validated.rejection_reasons)}"
            )
        if _sets(validated) != _sets(expected):
            raise ValueError(f"Expected output is not canonical in {case['id']}")
        case["inputs"], case["expected_output"] = inputs, expected
    return selected


def _fact_key(item) -> tuple:
    return (
        item.subject_entity_id or normalize_name(item.subject_text), item.predicate,
        item.object_entity_id or normalize_name(item.object_text), item.fact_type,
    )


def _event_key(item) -> tuple:
    return (
        item.event_type, tuple(sorted(item.participant_entity_ids)),
        tuple(sorted(item.location_entity_ids)),
        normalize_name(item.chronological_time_raw or ""),
    )


def _relationship_key(item) -> tuple:
    return (
        item.source_entity_id, item.relation_type, item.target_entity_id, item.change,
    )


def _sets(memory: ExtractedMemory | ValidatedMemory) -> dict[str, set[tuple]]:
    return {
        "facts": {_fact_key(item) for item in memory.facts},
        "events": {_event_key(item) for item in memory.events},
        "relationships": {_relationship_key(item) for item in memory.relationships},
    }


def _semantic_sets(memory: ExtractedMemory | ValidatedMemory) -> dict[str, set[tuple]]:
    sets = _sets(memory)
    sets["events"] = {
        (
            item.event_type, tuple(sorted(item.participant_entity_ids)),
            tuple(sorted(item.location_entity_ids)),
            normalize_name(item.chronological_time_raw or "").removeprefix("in "),
        )
        for item in memory.events
    }
    return sets


def _links(memory: ExtractedMemory | ValidatedMemory) -> set[tuple]:
    links = set()
    for item in memory.facts:
        if item.subject_entity_id:
            links.add(("fact", item.predicate, normalize_name(item.subject_text), "subject", item.subject_entity_id))
        if item.object_entity_id:
            links.add(("fact", item.predicate, normalize_name(item.object_text), "object", item.object_entity_id))
    for item in memory.events:
        for entity_id in item.participant_entity_ids:
            links.add(("event", item.event_type, "participant", entity_id))
        for entity_id in item.location_entity_ids:
            links.add(("event", item.event_type, "location", entity_id))
    for item in memory.relationships:
        if item.source_entity_id:
            links.add(("relationship", item.relation_type, "source", item.source_entity_id))
        if item.target_entity_id:
            links.add(("relationship", item.relation_type, "target", item.target_entity_id))
    return links


def _prf(predicted: set, expected: set) -> dict[str, float]:
    matched = len(predicted & expected)
    precision = matched / len(predicted) if predicted else (1.0 if not expected else 0.0)
    recall = matched / len(expected) if expected else (1.0 if not predicted else 0.0)
    return {
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }


def summarize(rows: list[dict]) -> dict:
    by_type = {}
    for kind in ("facts", "events", "relationships"):
        predicted = {(row["id"], tuple(item)) for row in rows for item in row["predicted"][kind]}
        expected = {(row["id"], tuple(item)) for row in rows for item in row["expected"][kind]}
        by_type[kind] = _prf(predicted, expected)
    semantic_by_type = {}
    for kind in ("facts", "events", "relationships"):
        predicted = {(row["id"], tuple(item)) for row in rows for item in row["semantic_predicted"][kind]}
        expected = {(row["id"], tuple(item)) for row in rows for item in row["semantic_expected"][kind]}
        semantic_by_type[kind] = _prf(predicted, expected)
    expected_links = {(row["id"], tuple(item)) for row in rows for item in row["expected_links"]}
    predicted_links = {(row["id"], tuple(item)) for row in rows for item in row["predicted_links"]}
    latencies = [row["latency_ms"] for row in rows]
    raw_count = sum(row["raw_count"] for row in rows)
    evidence_rejections = sum(
        reason.endswith("invalid_evidence_id")
        for row in rows for reason in row["rejection_reasons"]
    )
    return {
        "example_count": len(rows),
        "by_type": by_type,
        "macro_f1": statistics.mean(item["f1"] for item in by_type.values()),
        "semantic_by_type": semantic_by_type,
        "semantic_macro_f1": statistics.mean(item["f1"] for item in semantic_by_type.values()),
        "entity_link_accuracy": (
            len(expected_links & predicted_links) / len(expected_links) if expected_links else 1.0
        ),
        "entity_link_precision": (
            len(expected_links & predicted_links) / len(predicted_links) if predicted_links else 0.0
        ),
        "raw_evidence_validity": (
            1 - evidence_rejections / raw_count if raw_count else 1.0
        ),
        "accepted_evidence_validity": 1.0,
        "rejected_records": sum(row["rejected_count"] for row in rows),
        "repair_count": sum(row["repair_count"] for row in rows),
        "failed_examples": sum(bool(row["error"]) for row in rows),
        "p50_latency_ms": statistics.median(latencies),
        "p95_latency_ms": sorted(latencies)[round((len(latencies) - 1) * .95)],
        "llm_calls": len(rows) + sum(row["repair_count"] for row in rows),
        "tokens": {
            key: sum(row["usage"].get(key, 0) for row in rows)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        },
        "api_cost_usd": 0.0,
    }


async def evaluate(prompt_version: str, cases: list[dict], client: httpx.AsyncClient) -> dict:
    rows = []
    for case in cases:
        started = time.perf_counter()
        predicted = ValidatedMemory((), (), (), 0, ())
        result = None
        error = None
        repair_count = 0
        try:
            result = await extract_structured_memory(case["inputs"], prompt_version, client)
            predicted = result.memory
        except (StructuredMemoryError, ConnectionError, TimeoutError, httpx.HTTPError) as exc:
            error = type(exc).__name__
            repair_count = int(isinstance(exc, StructuredMemoryError))
        expected_sets, predicted_sets = _sets(case["expected_output"]), _sets(predicted)
        semantic_expected = _semantic_sets(case["expected_output"])
        semantic_predicted = _semantic_sets(predicted)
        rows.append({
            "id": case["id"],
            "expected": {key: sorted(value) for key, value in expected_sets.items()},
            "predicted": {key: sorted(value) for key, value in predicted_sets.items()},
            "semantic_expected": {key: sorted(value) for key, value in semantic_expected.items()},
            "semantic_predicted": {key: sorted(value) for key, value in semantic_predicted.items()},
            "expected_links": sorted(_links(case["expected_output"])),
            "predicted_links": sorted(_links(predicted)),
            "raw_count": result.raw_count if result else 0,
            "rejected_count": result.memory.rejected_count if result else 0,
            "rejection_reasons": list(result.memory.rejection_reasons) if result else [],
            "repair_count": result.repair_count if result else repair_count,
            "usage": result.usage if result else {},
            "latency_ms": result.latency_ms if result else (time.perf_counter() - started) * 1000,
            "resolved_model": result.model if result else None,
            "error": error,
        })
        print(json.dumps({"config": prompt_version, "case": case["id"], "error": error}), flush=True)
    return {
        "prompt_version": prompt_version,
        "prompt_sha256": hashlib.sha256(PROMPTS[prompt_version].encode()).hexdigest(),
        "metrics": summarize(rows),
        "rows": rows,
    }


async def run(split: str, experiment_version: str = "v7") -> dict:
    fixture, baseline_version, candidate_version = EXPERIMENTS[experiment_version]
    cases = load_cases(split, fixture)
    async with httpx.AsyncClient(
        base_url=os.environ["LITELLM_URL"],
        headers={"Authorization": f"Bearer {os.environ['LITELLM_API_KEY']}"},
        timeout=180,
    ) as client:
        baseline = await evaluate(baseline_version, cases, client)
        candidate = await evaluate(candidate_version, cases, client)
    return {
        "experiment_id": f"structured-memory-{experiment_version}-{split}-{uuid.uuid4().hex[:8]}",
        "diagnostic_only": True,
        "split": split,
        "fixture": str(fixture.relative_to(ROOT)),
        "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        "implementation_sha256": hashlib.sha256(IMPLEMENTATION.read_bytes()).hexdigest(),
        "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "example_ids": [case["id"] for case in cases],
        "baseline": baseline,
        "candidate": candidate,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("test",), default="test")
    parser.add_argument("--experiment-version", choices=tuple(EXPERIMENTS), default="v7")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(run(args.split, args.experiment_version))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "experiment_id": result["experiment_id"],
        "baseline": result["baseline"]["metrics"],
        "candidate": result["candidate"]["metrics"],
    }, indent=2))


if __name__ == "__main__":
    main()
