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
from app.ai.extraction_models import resolution_model_config
from langsmith import traceable, tracing_context
from app.db.models.entity_mention import EntityMention
from app.db.models.entity_resolution import ResolutionCandidate
from app.db.models.narrative import Chapter
from app.entity_resolution import candidate_pairs, make_pair, resolution_config

ROOT = Path(__file__).parents[2]
FIXTURE = Path(os.environ.get("STORYGUARD_DATA_DIR", ROOT / "data")) / "datasets/fixtures/entity_resolution_v2.jsonl"
TRANSIENT_EXPERIMENT_ERRORS = {
    "MODEL_RATE_LIMITED", "MODEL_SERVER_ERROR", "MODEL_TIMEOUT", "MODEL_CONNECTION_ERROR",
}


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
    predicted = sum(row[key] == "merge" and (key == "baseline" or not row["error"]) for row in rows)
    expected = sum(row["expected"] == "merge" for row in rows)
    tp = sum(row[key] == row["expected"] == "merge" and (key == "baseline" or not row["error"]) for row in rows)
    precision = tp / predicted if predicted else None
    recall = tp / expected if expected else None
    latencies = [row["latency_ms"] for row in rows] if key == "candidate" else [0.0] * len(rows)
    return {
        "merge_precision": precision, "merge_recall": recall,
        "pairwise_f1": 2 * tp / (predicted + expected) if predicted + expected else None,
        "incorrect_merge_count": predicted - tp,
        "incorrect_merge_rate": (predicted - tp) / predicted if predicted else None,
        "decision_accuracy": sum(row[key] == row["expected"] and (key == "baseline" or not row["error"]) for row in rows) / len(rows),
        "review_rate": sum(row[key] == "needs_review" and (key == "baseline" or not row["error"]) for row in rows) / len(rows),
        "error_rate": sum(bool(row["error"]) for row in rows) / len(rows) if key == "candidate" else 0,
        "p50_latency_ms": statistics.median(latencies),
        "p95_latency_ms": sorted(latencies)[round((len(latencies) - 1) * .95)],
        "api_cost_usd": 0,
    }


def gateway_metrics(rows: list[dict]) -> dict:
    called = [row for row in rows if row["candidate_generated"]]
    if not called:
        return {"evaluated_cases": len(rows), "model_cases": 0}
    result = metrics(called, "candidate")
    result.pop("api_cost_usd")  # Legacy metric assumes local-only inference.
    costs = [row["paid_tier_estimate_usd"] for row in called]
    calls = [call for row in called for call in row["gateway_calls"]]
    result.update(
        evaluated_cases=len(rows), model_cases=len(called),
        candidate_generation_misses=len(rows) - len(called),
        end_to_end_decision_accuracy=sum(
            row["candidate_generated"] and not row["error"] and row["candidate"] == row["expected"]
            for row in rows
        ) / len(rows),
        first_pass_valid_output_rate=sum(
            not row["error"] and not row["output_failures"]
            for row in called
        ) / len(called),
        repair_rate=sum(row["repair_count"] > 0 for row in called) / len(called),
        evidence_failure_cases=sum("evidence" in row["output_failures"] for row in called),
        fallback_rate=(sum(call["fallbacks"] > 0 for call in calls) / len(calls)
                       if calls and all(call.get("fallbacks") is not None for call in calls) else None),
        paid_tier_estimate_usd=sum(costs) if all(cost is not None for cost in costs) else None,
        billed_cost_usd=None,
        budget_exceeded_cases=sum(row["budget_exceeded"] for row in called),
    )
    return result


def gateway_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return ("MODEL_RATE_LIMITED" if status == 429 else
                "MODEL_SERVER_ERROR" if status >= 500 else "MODEL_REQUEST_REJECTED")
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return "MODEL_TIMEOUT"
    if isinstance(exc, (ConnectionError, httpx.TransportError)):
        return "MODEL_CONNECTION_ERROR"
    from app.ai.entity_resolution import EntityResolutionError
    from app.ai.entity_extraction import EntityExtractionError
    if isinstance(exc, (EntityResolutionError, EntityExtractionError)):
        return "INVALID_MODEL_OUTPUT"
    return "EXPERIMENT_ERROR"


def resumable_rows(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row.get("error") not in TRANSIENT_EXPERIMENT_ERRORS]


async def evaluate_gateway_case(case: dict, experiment: str, client: httpx.AsyncClient,
                                snapshot: dict) -> dict:
    pair, found = case_input(case)
    config = resolution_model_config(experiment)
    diagnostics = {key: snapshot[key] for key in ("experiment_id", "fixture_sha256", "routing_config_sha256")}
    diagnostics["case_id"] = case["id"]
    started = time.perf_counter()
    output, error, trace_id, repair_count = None, None, None, 0
    if found:
        try:
            result = await resolve_pair(pair, client, experiment=experiment, diagnostics=diagnostics)
            output, trace_id, repair_count = result.output.decision, result.trace_id, result.repair_count
        except Exception as exc:
            error = gateway_error(exc)
            trace_id = diagnostics.get("trace_id")
            repair_count = diagnostics.get("repair_count", 0)
    calls = diagnostics.get("gateway_calls", [])
    if not error and found and (any(call.get("fallbacks", 0) for call in calls)
            or any(config["provider_model"] not in str(call.get("resolved_model", "")) for call in calls)):
        error = "UNEXPECTED_MODEL_ROUTE"
    # An unsuccessful call may have incurred tokens without returning usage.
    usage_complete = bool(calls) and all(
        all(key in call.get("usage", {}) for key in ("prompt_tokens", "completion_tokens"))
        for call in calls
    )
    paid_cost = (0.0 if config.get("api_pricing") == "local" else sum(
        (call["usage"]["prompt_tokens"] * config["paid_input_usd_per_million"]
         + call["usage"]["completion_tokens"] * config["paid_output_usd_per_million"]) / 1_000_000
        for call in calls
    ) if usage_complete and all(key in config for key in (
        "paid_input_usd_per_million", "paid_output_usd_per_million")) else None)
    return {
        "id": case["id"], "expected": case["expected"], "candidate": output,
        "candidate_generated": found, "error": error,
        "latency_ms": (time.perf_counter() - started) * 1000,
        "repair_count": repair_count, "output_failures": diagnostics.get("output_failures", []),
        "gateway_calls": calls, "trace_id": trace_id,
        "pricing_basis": config.get("api_pricing", "mixed_provider"),
        "declared_tier_estimate_usd": 0.0 if found and config.get("api_pricing") in {"local", "user_declared_free_tier"} else None,
        "billed_cost_usd": None, "paid_tier_estimate_usd": paid_cost,
        "budget_exceeded": paid_cost is not None and paid_cost > .001,
    }


async def compare_gateway(split: str, output: Path, pause_seconds: float,
                          models: tuple[str, ...] = ("local", "gemini")) -> dict:
    """Fixed cases; a failed candidate checkpoints while other candidates continue."""
    cases = load_cases(split)
    routing_path = Path(os.environ.get("STORYGUARD_LITELLM_CONFIG", ROOT / "config/litellm.yaml"))
    behavior_sources = {str(path.relative_to(Path(__file__).parents[1])): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (Path(__file__).parents[1] / "app/ai" / name for name in
            ("entity_extraction.py", "entity_resolution.py", "extraction_models.py"))}
    evaluator_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    identity = {
        "split": split, "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "routing_config_sha256": hashlib.sha256(routing_path.read_bytes()).hexdigest(),
        "prompt_sha256": PROMPT_HASH, "prompt_version": PROMPT_VERSION,
        "models": {name: resolution_model_config(name) for name in models},
    }
    if output.exists():
        snapshot = json.loads(output.read_text())
        if any(snapshot.get(key) != value for key, value in identity.items()):
            raise ValueError("Existing experiment has different inputs/config; use a new output path")
        if any(snapshot.get("source_sha256", {}).get(key) != value for key, value in behavior_sources.items()):
            raise ValueError("Existing experiment used different model behavior code; use a new output path")
        if evaluator_sha256 not in snapshot.setdefault("evaluator_sha256_history", []):
            snapshot["evaluator_sha256_history"].append(evaluator_sha256)
        if snapshot.get("status") == "complete":
            return snapshot
    else:
        snapshot = {**identity, "experiment_id": f"gateway-v1-{split}-{uuid.uuid4().hex[:8]}",
                    "diagnostic_only": True, "example_count": len(cases),
                    "thresholds": {"accuracy_gain_pp": 5, "cost_usd_per_case": .001},
                    "source_sha256": {"scripts/entity_resolution_experiment.py": evaluator_sha256,
                                      **behavior_sources},
                    "evaluator_sha256_history": [evaluator_sha256],
                    "rows": {name: [] for name in models}}
    output.parent.mkdir(parents=True, exist_ok=True)

    def checkpoint(status):
        snapshot["status"] = status
        snapshot["metrics"] = {name: gateway_metrics(rows) for name, rows in snapshot["rows"].items()}
        output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")

    @traceable(name="model_gateway_experiment", run_type="chain",
               metadata={"experiment_id": snapshot["experiment_id"], "split": split})
    async def run():
        async with httpx.AsyncClient(base_url=os.environ["LITELLM_URL"],
                headers={"Authorization": f"Bearer {os.environ['LITELLM_API_KEY']}"}, timeout=180) as client:
            for name in models:
                config = resolution_model_config(name)
                snapshot["rows"][name] = resumable_rows(snapshot["rows"][name])
                done = {row["id"] for row in snapshot["rows"][name]}
                for case in cases:
                    if case["id"] in done:
                        continue
                    row = await evaluate_gateway_case(case, name, client, snapshot)
                    snapshot["rows"][name].append(row)
                    checkpoint("running")
                    print(json.dumps({"experiment": name, "case": case["id"],
                        "actual": row["candidate"], "error": row["error"],
                        "latency_ms": round(row["latency_ms"])}), flush=True)
                    # Requests are sequential. Never switch billing tier or retry exhausted quota.
                    if row["error"] in {"MODEL_RATE_LIMITED", "MODEL_REQUEST_REJECTED", "EXPERIMENT_ERROR", "UNEXPECTED_MODEL_ROUTE"}:
                        break
                    if config["provider"] != "ollama" and row["candidate_generated"]:
                        await asyncio.sleep(pause_seconds)
        checkpoint("complete" if all(len(rows) == len(cases) for rows in snapshot["rows"].values()) else "partial")
    # Synthetic fixtures only; keep default trace content metadata-only.
    with tracing_context(project_name=os.environ.get("LANGSMITH_PROJECT", "storyguard-local")):
        await run()
    return snapshot


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
    parser.add_argument("--gateway", action="store_true", help="Compare fixed aliases; no promotion")
    parser.add_argument("--gateway-models", nargs="+", default=("local", "gemini"),
                        help="Run one side separately, keeping the same comparison snapshot")
    parser.add_argument("--pause-seconds", type=float, default=15, help="Sequential Gemini request spacing")
    args = parser.parse_args()
    if args.pause_seconds < 0:
        parser.error("pause-seconds must be nonnegative")
    result = asyncio.run(compare_gateway(args.split, args.output, args.pause_seconds, tuple(args.gateway_models)) if args.gateway else evaluate(args.split))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, indent=2))


if __name__ == "__main__":
    main()
