from functools import lru_cache
from threading import Lock

from langsmith import traceable

from app.ai.entity_extraction import EntityExtractionError, EntityType, ResolvedMention


LABELS = tuple(entity_type.value for entity_type in EntityType)
GLINER_SCHEMA_VERSION = "gliner2.5-base-v1:labels-v1"
_INFERENCE_LOCK = Lock()


@lru_cache(maxsize=1)
def _model(repository: str, revision: str, device: str):
    from gliner2 import AutoExtractor

    return AutoExtractor.from_pretrained(
        repository, revision=revision, map_location=device
    )


def extract_predictions(model: object, text: str, threshold: float) -> tuple[set, int]:
    result = model.extract_entities(
        text,
        list(LABELS),
        threshold=threshold,
        include_confidence=True,
        include_spans=True,
    )
    if not isinstance(result, dict) or not isinstance(result.get("entities"), dict):
        raise ValueError("GLiNER returned an invalid entity payload")

    predictions = set()
    invalid_spans = 0
    for entity_type, mentions in result["entities"].items():
        if entity_type not in LABELS or not isinstance(mentions, list):
            invalid_spans += 1
            continue
        for mention in mentions:
            if not isinstance(mention, dict):
                invalid_spans += 1
                continue
            surface = mention.get("text")
            start = mention.get("start")
            end = mention.get("end")
            if (
                not isinstance(surface, str)
                or not surface
                or type(start) is not int
                or type(end) is not int
                or start < 0
                or end <= start
                or end > len(text)
                or text[start:end] != surface
            ):
                invalid_spans += 1
                continue
            predictions.add((start, end, entity_type))
    return predictions, invalid_spans


@traceable(
    name="gliner_entity_extraction",
    run_type="chain",
    process_inputs=lambda inputs: {
        "text_chars": len(inputs["text"]),
        "model": "gliner2.5-base-v1",
        "revision": inputs["config"]["revision"],
    },
    process_outputs=lambda output: {"mention_count": len(output)},
)
def extract_gliner(text: str, config: dict) -> tuple[ResolvedMention, ...]:
    # ponytail: one inference at a time per worker process; scale with worker capacity.
    with _INFERENCE_LOCK:
        model = _model(config["hf_repository"], config["revision"], config["device"])
        predicted, invalid = extract_predictions(model, text, config["threshold"])
    if invalid:
        raise EntityExtractionError("GLiNER spans failed source validation")
    return tuple(
        ResolvedMention(
            surface_text=text[start:end],
            entity_type=entity_type,
            start_offset=start,
            end_offset=end,
        )
        for start, end, entity_type in sorted(predicted)
    )
