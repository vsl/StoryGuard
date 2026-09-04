import argparse
import asyncio
import hashlib
import json
import os
import time
from pathlib import Path

import yaml

from app.ai.entity_extraction import PROMPTS, extract_entities
from scripts.entity_extraction_experiment import evaluate, load_cases


ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / "data" / "datasets" / "fixtures" / "entity_extraction_model_eval_v3.jsonl"
DEFAULT_MODELS_CONFIG = ROOT / "config" / "models.yaml"
PROMPT_VERSION = "entity_extractor:v3"
WARMUP_TEXT = "Ari entered Stonehaven."


def model_registry() -> tuple[Path, dict]:
    path = Path(os.environ.get("STORYGUARD_MODELS_CONFIG", DEFAULT_MODELS_CONFIG))
    registry = yaml.safe_load(path.read_text())["models"]["llms"][
        "entity_extraction"
    ]
    return path, registry


async def run(model_name: str) -> dict:
    config_path, registry = model_registry()
    model = registry["available"][model_name]
    started = time.perf_counter()
    await extract_entities(
        WARMUP_TEXT,
        PROMPT_VERSION,
        model_alias=model["litellm_alias"],
    )
    cold_start_latency_ms = (time.perf_counter() - started) * 1000
    result = await evaluate(
        PROMPT_VERSION,
        load_cases("test", FIXTURE),
        model_alias=model["litellm_alias"],
    )
    return {
        "dataset": {
            "fixture": str(FIXTURE.relative_to(ROOT)),
            "sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        },
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": hashlib.sha256(PROMPTS[PROMPT_VERSION].encode()).hexdigest(),
        "registry_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "default_model": registry["default"],
        "model": {"name": model_name, **model},
        "cold_start_latency_ms": cold_start_latency_ms,
        "metrics": result,
    }


def main() -> None:
    _, registry = model_registry()
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=tuple(registry["available"]), required=True)
    arguments = parser.parse_args()
    print(json.dumps(asyncio.run(run(arguments.model)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
