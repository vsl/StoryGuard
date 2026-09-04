import argparse
import asyncio
import hashlib
import json
import os
import statistics
import time
from pathlib import Path

import httpx

from app.ai.entity_extraction import (
    MODEL_ALIAS,
    PROMPTS,
    PROMPT_VERSION,
    EntityExtractionError,
    EntityType,
    extract_entities,
)


ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / "data" / "datasets" / "fixtures" / "entity_extraction_v3.jsonl"


def load_cases(split: str, fixture: Path = FIXTURE) -> list[dict]:
    cases = [json.loads(line) for line in fixture.read_text().splitlines()]
    selected = [case for case in cases if case["split"] == split]
    if not selected:
        raise ValueError("Entity extraction split is empty")
    for case in selected:
        for mention in case["mentions"]:
            if case["text"][mention["start_offset"] : mention["end_offset"]] != mention[
                "surface_text"
            ]:
                raise ValueError(f"Invalid labeled span in {case['id']}")
    return selected


def _key(mention: dict) -> tuple[int, int, str]:
    return (
        mention["start_offset"],
        mention["end_offset"],
        str(mention["entity_type"]),
    )


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * percentile)]


def _type_metrics(rows: list[dict]) -> tuple[dict[str, float], dict[str, dict[str, int]]]:
    per_type_recall = {}
    for entity_type in EntityType:
        expected = sum(
            item[2] == entity_type.value for row in rows for item in row["expected"]
        )
        matched = sum(
            item in row["predicted"] and item[2] == entity_type.value
            for row in rows
            for item in row["expected"]
        )
        per_type_recall[entity_type.value] = matched / expected if expected else 0.0

    confusion: dict[str, dict[str, int]] = {}
    for row in rows:
        expected = {(item[0], item[1]): item[2] for item in row["expected"]}
        predicted = {(item[0], item[1]): item[2] for item in row["predicted"]}
        for boundary in expected.keys() | predicted.keys():
            expected_type = expected.get(boundary, "__none__")
            predicted_type = predicted.get(boundary, "__missing__")
            targets = confusion.setdefault(expected_type, {})
            targets[predicted_type] = targets.get(predicted_type, 0) + 1
    return per_type_recall, confusion


def summarize_rows(rows: list[dict]) -> dict:
    true_positives = sum(row["true_positives"] for row in rows)
    expected_count = sum(len(row["expected"]) for row in rows)
    predicted_count = sum(len(row["predicted"]) for row in rows)
    boundary_matches = sum(row["boundary_matches"] for row in rows)
    invalid_spans = sum(row["invalid_spans"] for row in rows)
    precision = true_positives / predicted_count if predicted_count else 0.0
    recall = true_positives / expected_count if expected_count else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    latencies = [row["latency_ms"] for row in rows]
    per_type_recall, confusion = _type_metrics(rows)
    return {
        "example_count": len(rows),
        "expected_mentions": expected_count,
        "predicted_mentions": predicted_count,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "type_accuracy_on_boundary_matches": (
            sum(row["correctly_typed"] for row in rows) / boundary_matches
            if boundary_matches
            else 0.0
        ),
        "per_type_recall": per_type_recall,
        "type_confusion": confusion,
        "invalid_span_rate": (
            invalid_spans / (predicted_count + invalid_spans)
            if predicted_count + invalid_spans
            else 0.0
        ),
        "repair_count": sum(row["repair_count"] for row in rows),
        "failed_examples": sum(row["error"] is not None for row in rows),
        "failure_rate": sum(row["error"] is not None for row in rows) / len(rows),
        "p50_latency_ms": statistics.median(latencies),
        "p95_latency_ms": _percentile(latencies, 0.95),
        "api_cost_usd": 0.0,
        "failures": [
            row
            for row in rows
            if row["expected"] != row["predicted"]
            or row["invalid_spans"]
            or row["error"]
        ],
    }


async def evaluate(
    prompt_version: str,
    cases: list[dict],
    model_alias: str = MODEL_ALIAS,
) -> dict:
    rows = []
    async with httpx.AsyncClient(
        base_url=os.environ["LITELLM_URL"],
        headers={"Authorization": f"Bearer {os.environ['LITELLM_API_KEY']}"},
        timeout=120,
    ) as client:
        for case in cases:
            expected = {_key(mention) for mention in case["mentions"]}
            expected_boundaries = {
                (mention["start_offset"], mention["end_offset"]): mention["entity_type"]
                for mention in case["mentions"]
            }
            started = time.perf_counter()
            try:
                result = await extract_entities(
                    case["text"], prompt_version, client, model_alias
                )
            except (EntityExtractionError, ConnectionError, TimeoutError) as exc:
                rows.append(
                    {
                        "id": case["id"],
                        "text": case["text"],
                        "expected": sorted(expected),
                        "predicted": [],
                        "true_positives": 0,
                        "boundary_matches": 0,
                        "correctly_typed": 0,
                        "invalid_spans": 0,
                        "latency_ms": (time.perf_counter() - started) * 1000,
                        "repair_count": 1,
                        "resolved_model": None,
                        "error": type(exc).__name__,
                    }
                )
                continue
            predicted = {_key(mention.model_dump()) for mention in result.mentions}
            boundary_matches = [
                mention
                for mention in result.mentions
                if (mention.start_offset, mention.end_offset) in expected_boundaries
            ]
            correctly_typed = sum(
                expected_boundaries[(mention.start_offset, mention.end_offset)]
                == mention.entity_type
                for mention in boundary_matches
            )
            rows.append(
                {
                    "id": case["id"],
                    "text": case["text"],
                    "expected": sorted(expected),
                    "predicted": sorted(predicted),
                    "true_positives": len(expected & predicted),
                    "boundary_matches": len(boundary_matches),
                    "correctly_typed": correctly_typed,
                    "invalid_spans": len(result.invalid_mentions),
                    "latency_ms": result.latency_ms,
                    "repair_count": result.repair_count,
                    "resolved_model": result.model,
                    "error": None,
                }
            )

    return {
        "prompt_version": prompt_version,
        "prompt_sha256": hashlib.sha256(PROMPTS[prompt_version].encode()).hexdigest(),
        "model_alias": model_alias,
        "resolved_models": sorted(
            {row["resolved_model"] for row in rows if row["resolved_model"]}
        ),
        **summarize_rows(rows),
    }


async def run(split: str) -> dict:
    cases = load_cases(split)
    result = await evaluate(PROMPT_VERSION, cases)
    return {
        "dataset": {
            "split": split,
            "fixture": str(FIXTURE.relative_to(ROOT)),
            "sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            "example_ids": [case["id"] for case in cases],
        },
        "result": result,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    arguments = parser.parse_args()
    print(json.dumps(asyncio.run(run(arguments.split)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
