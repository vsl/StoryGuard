"""Server-owned upload choices; offline experiment candidates stay in the registry."""

import os
from enum import StrEnum
from pathlib import Path

import yaml


class ExtractionModel(StrEnum):
    GEMMA = "gemma4-e4b"
    GLINER = "gliner2.5-base-v1"
    QWEN = "qwen3.5-9b"


def _registry() -> dict:
    default = Path(__file__).parents[3] / "config" / "models.yaml"
    path = Path(os.environ.get("STORYGUARD_MODELS_CONFIG", default))
    return yaml.safe_load(path.read_text())["models"]


def default_extraction_model() -> ExtractionModel:
    return ExtractionModel(_registry()["llms"]["entity_extraction"]["default"])


def resolution_model_config() -> dict:
    config = _registry()["llms"]["entity_resolution"]
    selected = config["default"]
    available = config.get("available", {})
    if selected not in available:
        raise ValueError("Unknown entity-resolution model")
    return {**config, **available[selected]}


def extraction_model_config(model: str) -> dict:
    selected = ExtractionModel(model)  # Reject arbitrary model IDs and URLs.
    section = "extractors" if selected == ExtractionModel.GLINER else "llms"
    return _registry()[section]["entity_extraction"]["available"][selected]


def extraction_model_catalog() -> dict:
    return {
        "default": default_extraction_model(),
        "items": [
            {
                "id": ExtractionModel.GEMMA,
                "label": "gemma4:e4b",
                "description": "Quality default. Recommended for production; slower locally.",
            },
            {
                "id": ExtractionModel.GLINER,
                "label": "GLiNER2.5 Base",
                "description": "Fast CPU extraction for development; lower recall in our eval.",
            },
            {
                "id": ExtractionModel.QWEN,
                "label": "Qwen3.5 9B",
                "description": "Alternative local LLM; lower quality than Gemma in our eval.",
            },
        ],
    }
