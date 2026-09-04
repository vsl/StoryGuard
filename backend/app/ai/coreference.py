"""Source-validated coreference signals and a cancellable isolated runtime."""

import asyncio
import fcntl
import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path

from langsmith import traceable

from app.ai.tracing import annotate_trace
from scripts.coreference_predict import MODEL, REVISION, PIPELINE

BACKEND_ROOT = Path(__file__).parents[2]
SCRIPT = BACKEND_ROOT / "scripts" / "coreference_predict.py"
COREFERENCE_TIMEOUT_SECONDS = 1800


def cluster_membership(document: dict, text: str) -> dict:
    if document["text_sha256"] != hashlib.sha256(text.encode()).hexdigest():
        raise ValueError("Coreference cache belongs to different source text")
    membership: dict[tuple[int, int], set[tuple[int, int]]] = {}
    for window_index, window in enumerate(document["windows"]):
        for cluster_index, cluster in enumerate(window["clusters"]):
            for span in cluster:
                if (not isinstance(span, list) or len(span) != 2
                        or any(type(offset) is not int for offset in span)
                        or not 0 <= span[0] < span[1] <= len(text)):
                    raise ValueError("Invalid cached coreference source span")
                membership.setdefault(tuple(span), set()).add((window_index, cluster_index))
    return membership


def same_cluster(document: dict, text: str, left: tuple[int, int], right: tuple[int, int]) -> bool:
    """Absent links are unknown, never evidence for keeping entities separate."""
    membership = cluster_membership(document, text)
    a, b = membership.get(left, set()), membership.get(right, set())
    # Ambiguous span membership is not an accepted merge. Cluster IDs are window-local.
    return len(a) == len(b) == 1 and a == b


def validate_cache(cache: dict, documents: list[dict]) -> dict:
    if (cache.get("model"), cache.get("revision"), cache.get("pipeline")) != (MODEL, REVISION, PIPELINE):
        raise ValueError("Coreference cache model or pipeline changed")
    indexed = {doc["id"]: doc for doc in cache["documents"]}
    if len(indexed) != len(cache["documents"]) or set(indexed) != {doc["id"] for doc in documents}:
        raise ValueError("Coreference cache chapter scope changed")
    for doc in documents:
        cluster_membership(indexed[doc["id"]], doc["text"])
    return indexed


@traceable(
    name="resolution_coreference", run_type="chain",
    process_inputs=lambda inputs: {
        "manuscript_version_id": str(inputs["version_id"]),
        "document_count": len(inputs["documents"]),
        "text_chars": sum(len(doc["text"]) for doc in inputs["documents"]),
    },
    process_outputs=lambda cache: {
        "outcome": "ready", "cache_hit": cache["cache_hit"], "cache_key": cache["cache_key"],
        "model": cache["model"], "revision": cache["revision"],
        # Cache hits reference the original scan; they are not new inference time.
        "source_scan_trace_id": cache.get("trace_id"),
        "source_scan_load_ms": cache.get("load_ms"), "source_scan_wall_ms": cache.get("wall_ms"),
    } if cache else {},
    exceptions_to_handle=(Exception, asyncio.CancelledError),
)
async def load_coreference(version_id: uuid.UUID, documents: list[dict], check_running) -> dict:
    try:
        return await _load_coreference(version_id, documents, check_running)
    except (Exception, asyncio.CancelledError) as exc:
        # Record the class, never exception text containing paths or source data.
        annotate_trace(outputs={"outcome": "not_completed", "error_type": type(exc).__name__},
                       error_code=type(exc).__name__)
        raise


async def _load_coreference(version_id: uuid.UUID, documents: list[dict], check_running) -> dict:
    """One model load per uncached manuscript, not one load per pair.

    Completed caches survive Resume; stopping kills the subprocess and discards
    incomplete output. Only server-created chapter text/IDs enter this boundary.
    """
    root = Path(os.environ.get("STORYGUARD_LOCAL_DIR", BACKEND_ROOT.parent / ".local")) / "coreference" / str(uuid.UUID(str(version_id)))
    root.mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha256(
        json.dumps(documents, sort_keys=True).encode() + SCRIPT.read_bytes()
        + (BACKEND_ROOT / "scripts/coreference_requirements.txt").read_bytes()
    ).hexdigest()
    cache_path = root / f"{fingerprint}.json"
    await check_running()
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text())
            validate_cache(cache, documents)
            return {**cache, "cache_hit": True, "cache_key": fingerprint}
        except (ValueError, KeyError, TypeError):
            pass  # Recompute corrupt/stale derived data; never trust it for a merge.
    python = os.environ.get("STORYGUARD_COREFERENCE_PYTHON", str(BACKEND_ROOT.parent / ".local/xcore-venv/bin/python"))
    models = os.environ.get("STORYGUARD_COREFERENCE_MODELS", str(BACKEND_ROOT.parent / ".local/xcore-models"))
    # ponytail: one heavy coreference process per shared local cache. Raise
    # concurrency only after measuring the Docker memory budget.
    with tempfile.TemporaryDirectory(prefix="run-", dir=root) as temporary, (root.parent / ".inference.lock").open("a") as slot:
        deadline = asyncio.get_running_loop().time() + COREFERENCE_TIMEOUT_SECONDS
        async with asyncio.timeout_at(deadline):
            while True:
                await check_running()
                try:
                    fcntl.flock(slot, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    await asyncio.sleep(1)
        folder = Path(temporary)
        source, output = folder / "input.json", folder / "output.json"
        source.write_text(json.dumps({"documents": documents}))
        # No shell, user-selected executable, or provider/DB credentials in this process.
        environment = {key: value for key, value in os.environ.items()
                       if key in {"PATH", "HOME", "LANG", "SSL_CERT_FILE", "HF_TOKEN"} or key.startswith("LANGSMITH_")}
        environment.update(HF_HOME=models, PYTHONUNBUFFERED="1")
        process = await asyncio.create_subprocess_exec(
            python, str(SCRIPT), "--input", str(source), "--output", str(output), "--cache-dir", models,
            env=environment, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        waiter = asyncio.create_task(process.wait())
        try:
            async with asyncio.timeout_at(deadline):
                while True:
                    done, _ = await asyncio.wait({waiter}, timeout=1)
                    await check_running()
                    if done:
                        break
            if process.returncode:
                raise RuntimeError(f"Coreference process exited with code {process.returncode}")
            cache = json.loads(output.read_text())
            validate_cache(cache, documents)
            await check_running()
            output.replace(cache_path)  # Publish only a complete, validated cache atomically.
            return {**cache, "cache_hit": False, "cache_key": fingerprint}
        finally:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            await process.wait()
            await asyncio.gather(waiter, return_exceptions=True)
