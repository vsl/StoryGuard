"""Compare real Gemma calls with cached coreference + Gemma on the same cases.

Export input, run coreference_predict.py in the isolated environment, then compare.
This does not change the live resolver, apply story decisions, or promote a model.
"""

import argparse
import asyncio
import hashlib
import json
import os
import time
import uuid
from pathlib import Path

import httpx

from app.ai.coreference import same_cluster
from app.ai.entity_resolution import resolve_pair
from app.entity_resolution import resolution_config
from scripts.entity_resolution_experiment import FIXTURE, case_input, load_cases, metrics
from scripts.coreference_predict import MODEL, REVISION, PIPELINE


def documents(cases):
    return [{"id": case["id"], "text": case["text"].replace("{gap}", "The road was quiet. " * case.get("gap_repetitions", 0))} for case in cases]


async def compare(cases, cache):
    if (cache.get("model"), cache.get("revision"), cache.get("pipeline")) != (MODEL, REVISION, PIPELINE):
        raise ValueError("Unknown coreference model revision or pipeline")
    rows = []
    sources = {doc["id"]: doc for doc in documents(cases)}
    cached = {doc["id"]: doc for doc in cache["documents"]}
    if set(sources) != set(cached) or len(cached) != len(cache["documents"]):
        raise ValueError("Coreference cache and evaluation case IDs differ")
    config = resolution_config()
    timeout = config.get("request_timeout_seconds", 180)
    async with httpx.AsyncClient(base_url=os.environ["LITELLM_URL"],
            headers={"Authorization": f"Bearer {os.environ['LITELLM_API_KEY']}"}, timeout=timeout) as client:
        for case in cases:
            pair, found = case_input(case)
            linked = same_cluster(cached[case["id"]], sources[case["id"]]["text"],
                                  (pair.left.start_offset, pair.left.end_offset),
                                  (pair.right.start_offset, pair.right.end_offset))
            row = {"id": case["id"], "expected": case["expected"], "candidate_generated": found,
                   "coreference_merge": linked, "baseline": "needs_review", "candidate": "needs_review"}
            for arm in ("baseline", "candidate"):
                started = time.perf_counter()
                row[arm + "_calls"] = 0
                row[arm + "_error"] = None
                if arm == "candidate" and linked:
                    row[arm] = "merge"
                elif found:
                    try:
                        result = await resolve_pair(pair, client, request_timeout=timeout)
                        row[arm] = result.output.decision
                        row[arm + "_calls"] = 1 + result.repair_count
                        row[arm + "_trace_id"] = result.trace_id
                        row[arm + "_usage"] = result.usage
                    except Exception as exc:
                        row[arm + "_error"] = type(exc).__name__
                        row[arm + "_calls"] = None  # Never invent a failed request's call count.
                row[arm + "_ms"] = (time.perf_counter() - started) * 1000
            rows.append(row)
            print(json.dumps(row), flush=True)
    summaries = {}
    for arm in ("baseline", "candidate"):
        converted = [{**row, "candidate": row[arm], "latency_ms": row[arm + "_ms"],
                      "error": row[arm + "_error"]} for row in rows]
        summaries[arm] = {**metrics(converted, "candidate"),
                          "known_llm_calls": sum(row[arm + "_calls"] or 0 for row in rows),
                          "failed_call_counts_unknown": sum(row[arm + "_calls"] is None for row in rows),
                          "wall_ms": sum(row[arm + "_ms"] for row in rows)}
    summaries["candidate"]["wall_ms_including_cold_coreference"] = summaries["candidate"]["wall_ms"] + cache["wall_ms"]
    return {"experiment_id": "coreference-gemma-" + uuid.uuid4().hex[:12], "diagnostic_only": True,
            "policy": "same-cluster-exact-spans-v1", "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            "gemma": config, "coreference": {k: v for k, v in cache.items() if k != "documents"},
            **summaries, "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--export-input", type=Path)
    parser.add_argument("--coreference", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = load_cases(args.split)
    if args.export_input:
        args.export_input.parent.mkdir(parents=True, exist_ok=True)
        args.export_input.write_text(json.dumps({"documents": documents(cases)}) + "\n")
        return
    if not args.coreference or not args.output:
        parser.error("Provide --export-input or both --coreference and --output")
    result = asyncio.run(compare(cases, json.loads(args.coreference.read_text())))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}))


if __name__ == "__main__":
    main()
