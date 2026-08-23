from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
Loader = Callable[..., Iterable[Mapping[str, Any]]]


def _hf_loader(*args: Any, **kwargs: Any) -> Iterable[Mapping[str, Any]]:
    from datasets import load_dataset

    return load_dataset(*args, **kwargs)


def _text(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Expected non-empty string field: {key}")
    return value


def _row_bytes(row: Mapping[str, Any]) -> bytes:
    return json.dumps(
        row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _row_hash(row: Mapping[str, Any]) -> str:
    return hashlib.sha256(_row_bytes(row)).hexdigest()


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(_row_bytes(row) + b"\n" for row in rows)


def _select_ids(
    rows: Iterable[Mapping[str, Any]], key: str, selected_ids: list[str]
) -> list[Mapping[str, Any]]:
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError(f"Duplicate selected {key}")
    wanted = set(selected_ids)
    found: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        row_id = str(row.get(key, ""))
        if row_id in wanted:
            if row_id in found:
                raise ValueError(f"Duplicate source {key}: {row_id}")
            found[row_id] = row
            if len(found) == len(wanted):
                break
    missing = wanted - found.keys()
    if missing:
        raise ValueError(f"Missing selected {key}: {sorted(missing)}")
    return [found[row_id] for row_id in selected_ids]


def _select_indices(
    rows: Iterable[Mapping[str, Any]], selected_indices: list[int]
) -> list[Mapping[str, Any]]:
    if any(not isinstance(index, int) or index < 0 for index in selected_indices):
        raise ValueError("Selected row indices must be non-negative integers")
    if len(selected_indices) != len(set(selected_indices)):
        raise ValueError("Duplicate selected row index")
    wanted = set(selected_indices)
    found: dict[int, Mapping[str, Any]] = {}
    for index, row in enumerate(rows):
        if index in wanted:
            found[index] = row
            if len(found) == len(wanted):
                break
    missing = wanted - found.keys()
    if missing:
        raise ValueError(f"Missing selected row indices: {sorted(missing)}")
    return [found[index] for index in selected_indices]


def _load(
    loader: Loader, entry: Mapping[str, Any], config: str, **config_kwargs: Any
) -> Iterable[Mapping[str, Any]]:
    return loader(
        entry["hf_id"],
        config,
        revision=entry["revision"],
        split=entry["split"],
        streaming=True,
        **config_kwargs,
    )


def _fixture(path: str, rows: list[dict[str, Any]]) -> tuple[bytes, dict[str, Any]]:
    content = _jsonl(rows)
    return content, {
        "path": path,
        "count": len(rows),
        "sha256": hashlib.sha256(content).hexdigest(),
        "records": [
            {"id": row["id"], "sha256": _row_hash(row)} for row in rows
        ],
    }


def _source(entry: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    source = {
        "hf_id": entry["hf_id"],
        "revision": entry["revision"],
        "split": entry["split"],
        "provenance_url": entry["provenance_url"],
        "license_notes": entry["license_notes"],
        **extra,
    }
    if "source_revision" in entry:
        source["source_revision"] = entry["source_revision"]
    return source


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(dir=path.parent, delete=False)
    try:
        with temporary:
            temporary.write(content)
        os.replace(temporary.name, path)
    finally:
        Path(temporary.name).unlink(missing_ok=True)


def bootstrap(
    config_path: Path, root: Path = PROJECT_ROOT, loader: Loader = _hf_loader
) -> dict[str, Any]:
    registry = yaml.safe_load(config_path.read_text())
    if not isinstance(registry, dict) or registry.get("registry_version") != 1:
        raise ValueError("Unsupported dataset registry")
    entries = registry["datasets"]
    fixtures_dir = Path(registry["fixtures_dir"])
    outputs: dict[Path, bytes] = {}

    manuscripts = entries["public_domain_manuscripts"]
    manuscript_source = _select_ids(
        _load(
            loader,
            manuscripts,
            manuscripts["config"],
            filters=[("id", "in", manuscripts["selected_ids"])],
        ),
        "id",
        manuscripts["selected_ids"],
    )
    manuscript_rows = []
    for row in manuscript_source:
        metadata = row.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("license") != "Public Domain":
            raise ValueError(f"Gutenberg {row.get('id')} is not marked Public Domain")
        manuscript_rows.append(
            {
                "id": _text(row, "id"),
                "license": metadata["license"],
                "source_url": _text(metadata, "url"),
                "text": _text(row, "text"),
                "title": _text(metadata, "title"),
            }
        )
    manuscript_path = fixtures_dir / manuscripts["fixture"]
    outputs[manuscript_path], manuscript_fixture = _fixture(
        manuscript_path.as_posix(), manuscript_rows
    )

    story_qa = entries["story_qa"]
    qa_source = _select_indices(
        _load(loader, story_qa, story_qa["config"]), story_qa["selected_rows"]
    )
    qa_rows = []
    for index, row in zip(story_qa["selected_rows"], qa_source, strict=True):
        source = {
            "context": _text(row, "context"),
            "question": _text(row, "question"),
            "response": _text(row, "response"),
        }
        qa_rows.append(
            {
                "answer": source["response"],
                "context": source["context"],
                "id": _row_hash(source),
                "question": source["question"],
                "source_row": index,
            }
        )
    qa_path = fixtures_dir / story_qa["fixture"]
    outputs[qa_path], qa_fixture = _fixture(qa_path.as_posix(), qa_rows)

    retrieval = entries["retrieval_eval"]
    query_source = _select_indices(
        _load(loader, retrieval, retrieval["query_config"]),
        retrieval["selected_query_rows"],
    )
    query_rows = []
    for index, row in zip(
        retrieval["selected_query_rows"], query_source, strict=True
    ):
        source = {
            "answer": _text(row, "answer"),
            "chunk_id": _text(row, "chunk_id"),
            "query": _text(row, "query"),
        }
        query_rows.append(
            {
                "answer": source["answer"],
                "id": _row_hash(source),
                "query": source["query"],
                "relevant_chunk_id": source["chunk_id"],
                "source_row": index,
            }
        )
    chunk_ids = list(dict.fromkeys(row["relevant_chunk_id"] for row in query_rows))
    document_source = _select_ids(
        _load(loader, retrieval, retrieval["document_config"]),
        "chunk_id",
        chunk_ids,
    )
    document_rows = [
        {"id": _text(row, "chunk_id"), "text": _text(row, "chunk")}
        for row in document_source
    ]
    query_path = fixtures_dir / retrieval["query_fixture"]
    document_path = fixtures_dir / retrieval["document_fixture"]
    outputs[query_path], query_fixture = _fixture(query_path.as_posix(), query_rows)
    outputs[document_path], document_fixture = _fixture(
        document_path.as_posix(), document_rows
    )

    manifest = {
        "manifest_version": 1,
        "transform_version": registry["transform_version"],
        "datasets": {
            "public_domain_manuscripts": {
                **_source(
                    manuscripts,
                    config=manuscripts["config"],
                    selected_ids=manuscripts["selected_ids"],
                ),
                "fixture": manuscript_fixture,
            },
            "story_qa": {
                **_source(
                    story_qa,
                    config=story_qa["config"],
                    selected_rows=story_qa["selected_rows"],
                ),
                "fixture": qa_fixture,
            },
            "retrieval_eval": {
                **_source(
                    retrieval,
                    query_config=retrieval["query_config"],
                    document_config=retrieval["document_config"],
                    selected_query_rows=retrieval["selected_query_rows"],
                ),
                "fixtures": {
                    "queries": query_fixture,
                    "documents": document_fixture,
                },
            },
        },
    }
    manifest_path = root / registry["manifest_path"]
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        raise RuntimeError("Generated datasets differ from the committed manifest")

    for relative_path, content in outputs.items():
        _atomic_write(root / relative_path, content)
    _atomic_write(
        manifest_path,
        (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build pinned StoryGuard dataset fixtures")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config/datasets.yaml")
    args = parser.parse_args()
    manifest = bootstrap(args.config)
    for name, dataset in manifest["datasets"].items():
        fixtures = dataset["fixtures"] if "fixtures" in dataset else {"fixture": dataset["fixture"]}
        counts = ", ".join(f"{key}={value['count']}" for key, value in fixtures.items())
        print(f"{name}: {counts}")


if __name__ == "__main__":
    main()
