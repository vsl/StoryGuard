import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

from app import parsing as candidate


def _module(path: Path | None):
    if path is None:
        return candidate
    spec = importlib.util.spec_from_file_location("baseline_parsing", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load parser module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _score(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else 0.0
    )
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def _legacy_boundaries(parsed, text: str) -> dict[str, list[int]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    chapters = []
    for chapter in parsed.chapters:
        if chapter.title is None:
            continue
        matches = [
            index
            for index, line in enumerate(lines, 1)
            if line.strip().casefold() == chapter.title.strip().casefold()
        ]
        if not matches:
            raise ValueError(f"Cannot locate legacy chapter title: {chapter.title}")
        chapters.append(matches[-1])
    scene_count = sum(max(0, len(chapter.scenes) - 1) for chapter in parsed.chapters)
    if scene_count:
        raise ValueError("Legacy scene positions are unavailable")
    return {"chapters": chapters, "scenes": []}


def run(parser_module, fixture: Path, modern: Path, labels_path: Path) -> dict:
    rows = [json.loads(line) for line in fixture.read_text().splitlines()]
    rows.append({"id": "little-brother", "text": modern.read_text()})
    labels = json.loads(labels_path.read_text())
    chapter_totals = {"tp": 0, "fp": 0, "fn": 0}
    scene_totals = {"tp": 0, "fp": 0, "fn": 0}
    documents = []
    started = time.perf_counter()
    for row in rows:
        expected = labels["documents"][row["id"]]
        actual_hash = hashlib.sha256(row["text"].encode()).hexdigest()
        if actual_hash != expected["source_sha256"]:
            raise ValueError(f"Source hash mismatch for {row['id']}")
        parsed = parser_module.parse_manuscript(f"{row['id']}.txt", row["text"].encode())
        predicted = parsed.metadata.get("detected_boundaries") or _legacy_boundaries(
            parsed, row["text"]
        )
        differences = {}
        for kind, totals in (("chapters", chapter_totals), ("scenes", scene_totals)):
            predicted_lines = set(predicted[kind])
            expected_lines = set(expected[kind])
            totals["tp"] += len(predicted_lines & expected_lines)
            totals["fp"] += len(predicted_lines - expected_lines)
            totals["fn"] += len(expected_lines - predicted_lines)
            differences[kind] = {
                "false_lines": sorted(predicted_lines - expected_lines),
                "missing_lines": sorted(expected_lines - predicted_lines),
            }
        documents.append(
            {
                "id": row["id"],
                "chapters": len(parsed.chapters),
                "scenes": sum(len(chapter.scenes) for chapter in parsed.chapters),
                "chunks": sum(len(scene.chunks) for chapter in parsed.chapters for scene in chapter.scenes),
                "boundary_errors": differences,
                "warnings": parsed.metadata["warnings"],
            }
        )
    return {
        "parser_version": parser_module.PARSER_VERSION,
        "seconds": time.perf_counter() - started,
        "chapter_boundaries": _score(**chapter_totals),
        "scene_boundaries": _score(**scene_totals),
        "fallback_documents": sum(
            any(warning.startswith("No reliable chapter structure") for warning in document["warnings"])
            for document in documents
        ),
        "documents": documents,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=Path("data/datasets/fixtures/manuscripts.jsonl"))
    parser.add_argument("--modern", type=Path, required=True)
    parser.add_argument(
        "--labels",
        type=Path,
        default=Path("tests/fixtures/parser_boundaries.json"),
    )
    parser.add_argument("--baseline-module", type=Path)
    args = parser.parse_args()
    results = {"candidate": run(candidate, args.fixture, args.modern, args.labels)}
    if args.baseline_module:
        results["baseline"] = run(
            _module(args.baseline_module), args.fixture, args.modern, args.labels
        )
    print(json.dumps(results, indent=2))
