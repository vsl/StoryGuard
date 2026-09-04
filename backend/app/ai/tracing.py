import hashlib
import logging
import os
from dataclasses import asdict, is_dataclass
from functools import lru_cache
from typing import Any

from langsmith import get_current_run_tree, traceable


LOGGER = logging.getLogger(__name__)
TRACE_CONTENT_MODES = {"minimal", "redacted", "full"}
ID_FIELDS = {"chunk_id", "project_id", "manuscript_version_id", "chapter_id", "scene_id"}


def annotate_trace(*, metadata: dict | None = None, outputs: dict | None = None,
                   error_code: str | None = None) -> str | None:
    """Attach caller-allowlisted diagnostics; telemetry must never stop domain work."""
    try:
        run = get_current_run_tree()
        if run is not None:
            if metadata:
                run.add_metadata(metadata)
            if outputs:
                run.add_outputs(outputs)
            if error_code:
                run.error = error_code
            return str(run.id)
    except Exception:
        LOGGER.warning("LangSmith annotation unavailable")
    return None


@lru_cache(maxsize=1)
def trace_content_mode() -> str:
    mode = os.environ.get("LANGSMITH_TRACE_CONTENT", "minimal").lower()
    if mode not in TRACE_CONTENT_MODES:
        LOGGER.warning("Invalid LANGSMITH_TRACE_CONTENT; using minimal tracing")
        return "minimal"
    return mode


def _safe_id(value: object) -> str:
    return hashlib.sha256(str(value).encode()).hexdigest()[:12]


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _chunk(chunk: Any, mode: str) -> dict[str, Any]:
    data = _jsonable(chunk)
    if mode == "full":
        return data
    result = {
        key: (_safe_id(value) if key in ID_FIELDS and value is not None else value)
        for key, value in data.items()
        if key not in {"text", "content_hash"} and key != "embedding_version"
    }
    if data.get("embedding_version"):
        result["embedding_version"] = data["embedding_version"]
    if mode == "redacted":
        text = data.get("text", "")
        result["text"] = f"<redacted:{len(text)} chars>"
    return result


def _chunks(chunks: list[Any], mode: str) -> dict[str, Any]:
    if mode == "minimal":
        return {
            "count": len(chunks),
            "chunk_ids": [_safe_id(chunk.chunk_id) for chunk in chunks],
            "scores": [chunk.score for chunk in chunks],
        }
    return {"count": len(chunks), "chunks": [_chunk(chunk, mode) for chunk in chunks]}


def process_trace_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    mode = trace_content_mode()
    if mode == "full":
        return _jsonable(inputs)

    processed: dict[str, Any] = {}
    for key, value in inputs.items():
        if key == "query":
            processed["query_chars"] = len(value)
            if mode == "redacted":
                processed["query"] = f"<redacted:{len(value)} chars>"
        elif key in {"project_id", "manuscript_version_id"}:
            processed[key] = _safe_id(value)
        elif key == "candidates":
            processed["candidates"] = _chunks(value, mode)
        elif key == "rankings":
            processed["rankings"] = [_chunks(ranking, mode) for ranking in value]
        elif isinstance(value, (str, bytes)):
            if mode == "redacted":
                processed[key] = f"<redacted:{len(value)} chars>"
        else:
            processed[key] = _jsonable(value)
    return processed


def process_trace_outputs(outputs: Any) -> dict[str, Any]:
    if outputs is None:
        return {}
    return _chunks(outputs, trace_content_mode())


def traced(name: str, *, run_type: str = "retriever", **metadata: Any):
    return traceable(
        name=name,
        run_type=run_type,
        metadata=metadata,
        process_inputs=process_trace_inputs,
        process_outputs=process_trace_outputs,
    )
