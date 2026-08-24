import argparse
import json
import statistics
import time
from bisect import bisect_right
from pathlib import Path

from app.parsing import ChunkingConfig, ParsedManuscript, parse_manuscript, token_spans


def _chunks(parsed: ParsedManuscript):
    for chapter in parsed.chapters:
        for scene in chapter.scenes:
            for chunk in scene.chunks:
                yield chapter.ordinal, scene.ordinal, chunk


def _probes(parsed: ParsedManuscript, width: int = 40) -> list[tuple[int, int, int, int]]:
    probes = []
    for chapter in parsed.chapters:
        for scene in chapter.scenes:
            spans = token_spans(scene.text)
            token_ends = [end for _, end in spans]
            for chunk in scene.chunks[:-1]:
                boundary = chunk.end_offset - scene.start_offset
                token_index = bisect_right(token_ends, boundary)
                if token_index >= width and token_index + width <= len(spans):
                    probes.append(
                        (
                            chapter.ordinal,
                            scene.ordinal,
                            scene.start_offset + spans[token_index - width][0],
                            scene.start_offset + spans[token_index + width - 1][1],
                        )
                    )
    return probes


def run(fixture: Path) -> dict:
    rows = [json.loads(line) for line in fixture.read_text().splitlines()]
    configs = {
        "baseline": ChunkingConfig(overlap_tokens=0),
        "candidate": ChunkingConfig(overlap_tokens=100),
    }
    parsed_by_config: dict[str, list[ParsedManuscript]] = {}
    timings: dict[str, list[float]] = {}
    for name, config in configs.items():
        parsed_by_config[name], timings[name] = [], []
        for row in rows:
            started = time.perf_counter()
            parsed_by_config[name].append(
                parse_manuscript(f"{row['id']}.txt", row["text"].encode(), config)
            )
            timings[name].append(time.perf_counter() - started)

    baseline_probes = [_probes(parsed) for parsed in parsed_by_config["baseline"]]
    probe_count = sum(map(len, baseline_probes))
    results = {}
    for name, parsed_documents in parsed_by_config.items():
        chunks = [chunk for parsed in parsed_documents for _, _, chunk in _chunks(parsed)]
        source_tokens = sum(
            len(token_spans(scene.text))
            for parsed in parsed_documents
            for chapter in parsed.chapters
            for scene in chapter.scenes
        )
        embedded_tokens = sum(chunk.token_count for chunk in chunks)
        covered = invariant_failures = fallback_documents = 0
        for parsed, document_probes in zip(
            parsed_documents, baseline_probes, strict=True
        ):
            indexed = list(_chunks(parsed))
            covered += sum(
                any(
                    chapter == probe[0]
                    and scene == probe[1]
                    and chunk.start_offset <= probe[2]
                    and chunk.end_offset >= probe[3]
                    for chapter, scene, chunk in indexed
                )
                for probe in document_probes
            )
            fallback_documents += any(
                warning.startswith("No reliable chapter structure")
                for warning in parsed.metadata["warnings"]
            )
            invariant_failures += sum(
                chunk.token_count > configs[name].max_tokens
                or chapter.text[chunk.start_offset : chunk.end_offset] != chunk.text
                or not (
                    scene.start_offset
                    <= chunk.start_offset
                    < chunk.end_offset
                    <= scene.end_offset
                )
                for chapter in parsed.chapters
                for scene in chapter.scenes
                for chunk in scene.chunks
            )
        results[name] = {
            "config": parsed_documents[0].metadata["chunking"],
            "boundary_probe_count": probe_count,
            "boundary_coverage": covered / probe_count if probe_count else 1.0,
            "chunk_count": len(chunks),
            "source_tokens": source_tokens,
            "estimated_embedding_tokens": embedded_tokens,
            "duplicate_token_ratio": (embedded_tokens - source_tokens) / source_tokens,
            "median_seconds": statistics.median(timings[name]),
            "fallback_documents": fallback_documents,
            "invariant_failures": invariant_failures,
        }
    return {"fixture": str(fixture), "documents": len(rows), "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "fixture",
        type=Path,
        nargs="?",
        default=Path("data/datasets/fixtures/manuscripts.jsonl"),
    )
    print(json.dumps(run(parser.parse_args().fixture), indent=2))
