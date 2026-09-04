"""Frozen diagnostic: all-review baseline vs the production candidate+Gemma path."""

import argparse
import asyncio
import hashlib
import json
import os
import re
import statistics
import time
import uuid
from pathlib import Path

import httpx

from app.ai.entity_resolution import PROMPT_HASH, PROMPT_VERSION, resolve_pair
from app.db.models.entity_mention import EntityMention
from app.db.models.entity_resolution import ResolutionCandidate
from app.db.models.narrative import Chapter
from app.entity_resolution import candidate_pairs, make_pair, resolution_config

ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / "data/datasets/fixtures/entity_resolution_v2.jsonl"


def load_cases(split: str) -> list[dict]:
    cases = [json.loads(line) for line in FIXTURE.read_text().splitlines() if line.strip()]
    return [case for case in cases if case["split"] == split]


def case_input(case: dict):
    text = case["text"].replace("{gap}", "The road was quiet. " * case.get("gap_repetitions", 0))
    version_id = uuid.uuid5(uuid.NAMESPACE_URL, "resolution-eval:" + case["id"])
    chapter_id = uuid.uuid5(version_id, "chapter")
    chapter = Chapter(id=chapter_id, manuscript_version_id=version_id, ordinal=1,
                      title="Evaluation passage", text=text, content_hash=hashlib.sha256(text.encode()).hexdigest())
    mentions = []
    for index, description in enumerate([case["left"], case["right"], *case.get("distractors", [])]):
        matches = list(re.finditer(r"(?<!\w)" + re.escape(description["text"]) + r"(?!\w)", text))
        match = matches[description.get("occurrence", 0)]
        mention_id = uuid.uuid5(version_id, f"mention:{index}")
        mentions.append(EntityMention(id=mention_id, manuscript_version_id=version_id,
            chapter_id=chapter_id, scene_id=None, chunk_id=uuid.uuid5(version_id, "chunk"),
            entity_type=case["type"], surface_text=match.group(), start_offset=match.start(), end_offset=match.end()))
    left_id, right_id = sorted((mentions[0].id, mentions[1].id))
    candidate = ResolutionCandidate(id=uuid.uuid5(version_id, "candidate"), manuscript_version_id=version_id,
                                    left_mention_id=left_id, right_mention_id=right_id)
    pair = make_pair(candidate, {mention.id: (mention, chapter) for mention in mentions})
    found = (left_id, right_id) in candidate_pairs(sorted(mentions, key=lambda item: item.start_offset))
    return pair, found


def metrics(rows: list[dict], key: str) -> dict:
    predicted = sum(row[key] == "merge" for row in rows)
    expected = sum(row["expected"] == "merge" for row in rows)
    tp = sum(row[key] == row["expected"] == "merge" for row in rows)
    precision = tp / predicted if predicted else None
    recall = tp / expected if expected else None
    latencies = [row["latency_ms"] for row in rows] if key == "candidate" else [0.0] * len(rows)
    return {
        "merge_precision": precision, "merge_recall": recall,
        "pairwise_f1": 2 * tp / (predicted + expected) if predicted + expected else None,
        "incorrect_merge_count": predicted - tp,
        "incorrect_merge_rate": (predicted - tp) / predicted if predicted else None,
        "decision_accuracy": sum(row[key] == row["expected"] for row in rows) / len(rows),
        "review_rate": sum(row[key] == "needs_review" for row in rows) / len(rows),
        "error_rate": sum(bool(row["error"]) for row in rows) / len(rows) if key == "candidate" else 0,
        "p50_latency_ms": statistics.median(latencies),
        "p95_latency_ms": sorted(latencies)[round((len(latencies) - 1) * .95)],
        "api_cost_usd": 0,
    }


async def evaluate(split: str) -> dict:
    cases = load_cases(split)
    if not cases:
        raise ValueError("Empty resolution split")
    rows = []
    timeout = resolution_config().get("request_timeout_seconds", 180)
    async with httpx.AsyncClient(base_url=os.environ["LITELLM_URL"],
            headers={"Authorization": f"Bearer {os.environ['LITELLM_API_KEY']}"}, timeout=timeout) as client:
        for case in cases:
            pair, found = case_input(case)
            started = time.perf_counter()
            output, error, metadata = "needs_review", None, {}
            if found:
                try:
                    async with asyncio.timeout(2 * timeout):
                        result = await resolve_pair(pair, client, request_timeout=timeout)
                    output = result.output.decision
                    metadata = {"resolved_model": result.model, "repair_count": result.repair_count,
                                "usage": result.usage, "trace_id": result.trace_id}
                except Exception as exc:
                    error = type(exc).__name__
            rows.append({"id": case["id"], "expected": case["expected"], "baseline": "needs_review",
                         "candidate": output, "candidate_generated": found, "error": error,
                         "latency_ms": (time.perf_counter() - started) * 1000, **metadata})
            print(json.dumps({"case": case["id"], "expected": case["expected"], "actual": output,
                              "candidate_generated": found, "error": error}), flush=True)
    positives = [row for row in rows if row["expected"] == "merge"]
    return {
        "experiment_id": f"entity-resolution-v2-{split}-{uuid.uuid4().hex[:8]}",
        "diagnostic_only": True, "split": split, "example_count": len(rows),
        "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "prompt_version": PROMPT_VERSION, "prompt_sha256": PROMPT_HASH,
        "model_alias": resolution_config()["litellm_alias"], "model_config": resolution_config(),
        "candidate_generation_recall": sum(row["candidate_generated"] for row in positives) / len(positives),
        "baseline": metrics(rows, "baseline"), "candidate": metrics(rows, "candidate"),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("dev", "test"), default="test")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(evaluate(args.split))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, indent=2))


if __name__ == "__main__":
    main()
