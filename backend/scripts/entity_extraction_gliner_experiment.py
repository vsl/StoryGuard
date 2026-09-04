import argparse
import hashlib
import importlib.metadata
import json
import os
import resource
import sys
import time
from pathlib import Path

import yaml

from app.ai.gliner_extraction import LABELS, extract_predictions
from scripts.entity_extraction_experiment import load_cases, summarize_rows


ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / "data" / "datasets" / "fixtures" / "entity_extraction_model_eval_v3.jsonl"
DEFAULT_MODELS_CONFIG = ROOT / "config" / "models.yaml"
EXPERIMENT_ID = "entity-extraction-gliner25-labels-v2-20260831"
WARMUP_TEXT = "Ari entered Stonehaven."


def model_registry() -> tuple[Path, dict, str]:
    path = Path(os.environ.get("STORYGUARD_MODELS_CONFIG", DEFAULT_MODELS_CONFIG))
    models = yaml.safe_load(path.read_text())["models"]
    default = models["llms"]["entity_extraction"]["default"]
    return path, models["extractors"]["entity_extraction"], default


def _peak_rss_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024


def evaluate(model: object, cases: list[dict], model_name: str, threshold: float) -> dict:
    rows = []
    for case in cases:
        expected = {
            (
                mention["start_offset"],
                mention["end_offset"],
                mention["entity_type"],
            )
            for mention in case["mentions"]
        }
        expected_boundaries = {
            (mention["start_offset"], mention["end_offset"]): mention["entity_type"]
            for mention in case["mentions"]
        }
        started = time.perf_counter()
        try:
            predicted, invalid_spans = extract_predictions(
                model, case["text"], threshold
            )
            error = None
        except (RuntimeError, TypeError, ValueError) as exc:
            predicted, invalid_spans = set(), 0
            error = type(exc).__name__
        latency_ms = (time.perf_counter() - started) * 1000
        boundary_matches = [
            item for item in predicted if (item[0], item[1]) in expected_boundaries
        ]
        correctly_typed = sum(
            expected_boundaries[(item[0], item[1])] == item[2]
            for item in boundary_matches
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
                "invalid_spans": invalid_spans,
                "latency_ms": latency_ms,
                "repair_count": 0,
                "resolved_model": model_name,
                "error": error,
            }
        )
    return summarize_rows(rows)


def run(model_name: str) -> dict:
    from gliner2 import AutoExtractor

    config_path, registry, default_model = model_registry()
    config = registry["available"][model_name]
    rss_before = _peak_rss_mb()
    load_started = time.perf_counter()
    model = AutoExtractor.from_pretrained(
        config["hf_repository"],
        revision=config["revision"],
        map_location=config["device"],
    )
    load_latency_ms = (time.perf_counter() - load_started) * 1000
    warmup_started = time.perf_counter()
    extract_predictions(model, WARMUP_TEXT, config["threshold"])
    first_inference_latency_ms = (time.perf_counter() - warmup_started) * 1000
    metrics = evaluate(
        model,
        load_cases("test", FIXTURE),
        model_name,
        config["threshold"],
    )
    return {
        "experiment_id": EXPERIMENT_ID,
        "dataset": {
            "fixture": str(FIXTURE.relative_to(ROOT)),
            "sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        },
        "labels": list(LABELS),
        "label_descriptions": False,
        "registry_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "default_model": default_model,
        "candidate": {"name": model_name, **config},
        "installed_package_version": importlib.metadata.version("gliner2"),
        "load_latency_ms": load_latency_ms,
        "first_inference_latency_ms": first_inference_latency_ms,
        "cold_start_latency_ms": load_latency_ms + first_inference_latency_ms,
        "peak_rss_mb": _peak_rss_mb(),
        "peak_rss_increase_mb": max(0.0, _peak_rss_mb() - rss_before),
        "metrics": metrics,
    }


def main() -> None:
    _, registry, _ = model_registry()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model", choices=tuple(registry["available"]), default="gliner2.5-base-v1"
    )
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.model), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
