import hashlib
import io
import re
import zipfile
from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from pathlib import PurePath

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

PARSER_VERSION = "v2"
TOKENIZER_VERSION = "regex-v1"
TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)
SCENE_RE = re.compile(r"^(?:\*\s*\*\s*\*|---)$")
CHAPTER_RE = re.compile(
    r"^(?:chapter\s+(?:\d+|[ivxlcdm]+)\.?(?:(?:\s*[:\-\u2013\u2014]\s*|\s+)\S.*)?"
    r"|prologue\.?(?:(?:\s*[:\-\u2013\u2014]\s*|\s+)\S.*)?"
    r"|epilogue\.?(?:(?:\s*[:\-\u2013\u2014]\s*|\s+)\S.*)?)$",
    re.IGNORECASE,
)
MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)(?:\s+#+)?$")
NUMBER_HEADING_RE = re.compile(r"^(\d+)$")
ROMAN_TITLE_RE = re.compile(r"^([ivxlcdm]+)\.\s+\S.*$", re.IGNORECASE)


@dataclass(frozen=True)
class ChunkingConfig:
    target_tokens: int = 700
    max_tokens: int = 900
    overlap_tokens: int = 100
    version: str = "storyguard-700-900-v1"

    def __post_init__(self) -> None:
        if not 0 <= self.overlap_tokens < self.target_tokens <= self.max_tokens:
            raise ValueError("Chunking requires 0 <= overlap < target <= maximum")


@dataclass(frozen=True)
class ParsedChunk:
    text: str
    start_offset: int
    end_offset: int
    token_count: int
    content_hash: str


@dataclass
class ParsedScene:
    ordinal: int
    text: str
    start_offset: int
    end_offset: int
    content_hash: str
    chunks: list[ParsedChunk] = field(default_factory=list)


@dataclass
class ParsedChapter:
    ordinal: int
    title: str | None
    text: str
    content_hash: str
    scenes: list[ParsedScene] = field(default_factory=list)


@dataclass
class ParsedManuscript:
    chapters: list[ParsedChapter]
    metadata: dict


@dataclass(frozen=True)
class _Block:
    text: str
    heading: bool = False
    scene_break: bool = False
    break_after: bool = False
    source_line: int | None = None


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def token_spans(text: str) -> list[tuple[int, int]]:
    return [(match.start(), match.end()) for match in TOKEN_RE.finditer(text)]


def _text_blocks(text: str, markdown: bool) -> list[_Block]:
    blocks: list[_Block] = []
    paragraph: list[str] = []
    paragraph_start_line: int | None = None

    def flush() -> None:
        nonlocal paragraph_start_line
        if paragraph:
            blocks.append(
                _Block(
                    "\n".join(paragraph).strip(),
                    source_line=paragraph_start_line,
                )
            )
            paragraph.clear()
            paragraph_start_line = None

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        markdown_match = MARKDOWN_HEADING_RE.fullmatch(line) if markdown else None
        if not line:
            flush()
        elif markdown_match:
            flush()
            blocks.append(
                _Block(
                    markdown_match.group(1).strip(),
                    heading=True,
                    source_line=line_number,
                )
            )
        elif SCENE_RE.fullmatch(line) or (not markdown and line == "#"):
            flush()
            blocks.append(_Block(line, scene_break=True, source_line=line_number))
        elif not markdown and CHAPTER_RE.fullmatch(line):
            flush()
            blocks.append(_Block(line, heading=True, source_line=line_number))
        else:
            if not paragraph:
                paragraph_start_line = line_number
            paragraph.append(raw_line.rstrip())
    flush()
    return blocks


def _roman_value(value: str) -> int:
    numbers = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = previous = 0
    for character in reversed(value.upper()):
        current = numbers[character]
        total += -current if current < previous else current
        previous = max(previous, current)
    return total


def _sequence_indices(
    blocks: list[_Block], pattern: re.Pattern[str], roman: bool = False
) -> set[int]:
    candidates = []
    for index, block in enumerate(blocks):
        match = pattern.fullmatch(block.text)
        if match:
            value = _roman_value(match.group(1)) if roman else int(match.group(1))
            candidates.append((index, value))

    run: list[int] = []
    accepted: set[int] = set()
    previous_index = previous_value = None
    for index, value in candidates:
        body_size = (
            sum(len(block.text) for block in blocks[previous_index + 1 : index])
            if previous_index is not None
            else 0
        )
        if value == 1:
            if len(run) >= 3:
                accepted.update(run)
            run = [index]
        elif run and value == previous_value + 1 and body_size >= 200:
            run.append(index)
        else:
            if len(run) >= 3:
                accepted.update(run)
            run = []
        previous_index, previous_value = index, value
    if len(run) >= 3:
        accepted.update(run)
    return accepted


def _mark_sequence_headings(blocks: list[_Block]) -> list[_Block]:
    headings = _sequence_indices(blocks, NUMBER_HEADING_RE)
    headings.update(_sequence_indices(blocks, ROMAN_TITLE_RE, roman=True))
    return [replace(block, heading=True) if index in headings else block for index, block in enumerate(blocks)]


def _has_document_break(paragraph: Paragraph) -> bool:
    return bool(
        paragraph._p.xpath("./w:pPr/w:sectPr")
        or paragraph._p.xpath(".//w:br[@w:type='page']")
    )


def _docx_blocks(data: bytes, max_uncompressed_bytes: int) -> list[_Block]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 10_000:
                raise ValueError("DOCX archive contains too many entries")
            if sum(entry.file_size for entry in entries) > max_uncompressed_bytes:
                raise ValueError("DOCX archive expands beyond the safe limit")
            names = {entry.filename for entry in entries}
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise ValueError("Malformed DOCX manuscript")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError("Malformed DOCX manuscript") from exc
    try:
        document = Document(io.BytesIO(data))
    except Exception as exc:
        raise ValueError("Malformed DOCX manuscript") from exc

    blocks: list[_Block] = []
    for item in document.iter_inner_content():
        if isinstance(item, Paragraph):
            text = item.text.strip()
            if text:
                style = item.style.name if item.style is not None else ""
                blocks.append(
                    _Block(
                        text,
                        heading=style.casefold().startswith("heading "),
                        scene_break=bool(SCENE_RE.fullmatch(text)),
                        break_after=_has_document_break(item),
                    )
                )
            elif _has_document_break(item) and blocks:
                previous = blocks[-1]
                blocks[-1] = _Block(
                    previous.text,
                    previous.heading,
                    previous.scene_break,
                    break_after=True,
                )
        elif isinstance(item, Table):
            rows = ["\t".join(cell.text.strip() for cell in row.cells) for row in item.rows]
            text = "\n".join(row for row in rows if row.strip())
            if text:
                blocks.append(_Block(text))
    return blocks


def _split_chapters(
    blocks: list[_Block],
) -> tuple[list[tuple[str | None, list[_Block]]], list[str]]:
    headings = [index for index, block in enumerate(blocks) if block.heading]
    if not headings:
        return [(None, blocks)], ["No reliable chapter structure; used one chapter"]

    chapters: list[tuple[str | None, list[_Block]]] = []
    preamble = [
        replace(block, scene_break=False, break_after=False)
        for block in blocks[: headings[0]]
    ]
    for position, heading_index in enumerate(headings):
        end = headings[position + 1] if position + 1 < len(headings) else len(blocks)
        body = blocks[heading_index + 1 : end]
        if position == 0:
            body = preamble + body
        chapters.append((blocks[heading_index].text, body))
    return chapters, []


def _chapter_key(text: str) -> str | None:
    match = re.match(r"^chapter\s+(\d+|[ivxlcdm]+)\b", text.strip(), re.IGNORECASE)
    if match:
        return f"chapter:{match.group(1).upper()}"
    match = re.match(r"^(prologue|epilogue)\b", text.strip(), re.IGNORECASE)
    if match:
        return match.group(1).casefold()
    match = NUMBER_HEADING_RE.fullmatch(text.strip())
    if match:
        return f"number:{int(match.group(1))}"
    match = ROMAN_TITLE_RE.fullmatch(text.strip())
    return f"roman:{_roman_value(match.group(1))}" if match else None


def _prefer_last_duplicate_headings(
    blocks: list[_Block],
) -> tuple[list[_Block], list[str]]:
    keys = [_chapter_key(block.text) if block.heading else None for block in blocks]
    counts = Counter(key for key in keys if key is not None)
    duplicates = {key for key, count in counts.items() if count > 1}
    if not duplicates:
        return blocks, []
    last = {key: index for index, key in enumerate(keys) if key in duplicates}
    removed = 0
    filtered = []
    for index, (block, key) in enumerate(zip(blocks, keys, strict=True)):
        if key in duplicates and index != last[key]:
            filtered.append(replace(block, heading=False))
            removed += 1
        else:
            filtered.append(block)
    return filtered, [f"Ignored {removed} duplicate chapter markers before final occurrences"]


def _scene_ranges(
    blocks: list[_Block],
) -> tuple[str, list[tuple[int, int]], list[int]]:
    parts: list[str] = []
    ranges: list[tuple[int, int]] = []
    boundary_lines: list[int] = []
    cursor = 0
    scene_start: int | None = None
    scene_end: int | None = None
    pending_boundary_line: int | None = None

    def append(text: str) -> tuple[int, int]:
        nonlocal cursor
        if parts:
            parts.append("\n\n")
            cursor += 2
        start = cursor
        parts.append(text)
        cursor += len(text)
        return start, cursor

    def close_scene() -> None:
        nonlocal scene_start, scene_end
        if scene_start is not None and scene_end is not None:
            ranges.append((scene_start, scene_end))
        scene_start = scene_end = None

    for block in blocks:
        if block.scene_break:
            had_scene = scene_start is not None and scene_end is not None
            close_scene()
            if had_scene and pending_boundary_line is None:
                pending_boundary_line = block.source_line
            append(block.text)
            continue
        start, end = append(block.text)
        if scene_start is None and pending_boundary_line is not None:
            boundary_lines.append(pending_boundary_line)
            pending_boundary_line = None
        scene_start = start if scene_start is None else scene_start
        scene_end = end
        if block.break_after:
            close_scene()
    close_scene()
    return "".join(parts), ranges, boundary_lines


def _chunk_scene(
    chapter_text: str, scene_start: int, scene_end: int, config: ChunkingConfig
) -> list[ParsedChunk]:
    scene_text = chapter_text[scene_start:scene_end]
    spans = token_spans(scene_text)
    if not spans:
        return []

    ends = [end for _, end in spans]
    boundary_chars = [
        match.end()
        for match in re.finditer(
            r"\n\s*\n|[.!?][\"'\u2019\u201d)]*(?:\s+|$)", scene_text
        )
    ]
    boundaries = sorted(
        {bisect_right(ends, char) for char in boundary_chars} | {len(spans)}
    )

    chunks: list[ParsedChunk] = []
    start_token = 0
    while start_token < len(spans):
        target = min(start_token + config.target_tokens, len(spans))
        maximum = min(start_token + config.max_tokens, len(spans))
        boundary_index = bisect_left(boundaries, target)
        boundary = boundaries[boundary_index]
        end_token = boundary if boundary <= maximum else maximum
        start_char = spans[start_token][0]
        end_char = spans[end_token - 1][1]
        text = scene_text[start_char:end_char]
        chunks.append(
            ParsedChunk(
                text=text,
                start_offset=scene_start + start_char,
                end_offset=scene_start + end_char,
                token_count=end_token - start_token,
                content_hash=_hash(text),
            )
        )
        if end_token == len(spans):
            break
        start_token = end_token - config.overlap_tokens
    return chunks


def parse_manuscript(
    filename: str,
    data: bytes,
    config: ChunkingConfig = ChunkingConfig(),
    docx_max_uncompressed_bytes: int = 200 * 1024 * 1024,
) -> ParsedManuscript:
    suffix = PurePath(filename).suffix.casefold()
    detection_warnings: list[str] = []
    if suffix == ".docx":
        blocks = _docx_blocks(data, docx_max_uncompressed_bytes)
        if any(block.heading for block in blocks):
            detection = "docx_heading_style"
        else:
            blocks = [
                _Block(
                    block.text,
                    heading=bool(CHAPTER_RE.fullmatch(block.text)),
                    scene_break=block.scene_break,
                    break_after=block.break_after,
                )
                for block in blocks
            ]
            detection = "docx_chapter_regex"
            blocks, detection_warnings = _prefer_last_duplicate_headings(blocks)
    elif suffix in {".md", ".txt"}:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Text manuscripts must use UTF-8") from exc
        blocks = _text_blocks(text, markdown=suffix == ".md")
        detection = "markdown_heading" if suffix == ".md" else "text_chapter_regex"
        if suffix == ".txt":
            blocks = _mark_sequence_headings(blocks)
            blocks, detection_warnings = _prefer_last_duplicate_headings(blocks)
    else:
        raise ValueError("Unsupported manuscript file type")
    if not blocks:
        raise ValueError("Manuscript contains no readable text")

    raw_chapters, warnings = _split_chapters(blocks)
    warnings = detection_warnings + warnings
    chapters: list[ParsedChapter] = []
    scene_boundary_lines: list[int] = []
    for chapter_ordinal, (title, body) in enumerate(raw_chapters, 1):
        chapter_text, ranges, chapter_scene_lines = _scene_ranges(body)
        scene_boundary_lines.extend(chapter_scene_lines)
        scenes: list[ParsedScene] = []
        for scene_ordinal, (start, end) in enumerate(ranges, 1):
            scene_text = chapter_text[start:end]
            scenes.append(
                ParsedScene(
                    ordinal=scene_ordinal,
                    text=scene_text,
                    start_offset=start,
                    end_offset=end,
                    content_hash=_hash(scene_text),
                    chunks=_chunk_scene(chapter_text, start, end, config),
                )
            )
        chapters.append(
            ParsedChapter(
                ordinal=chapter_ordinal,
                title=title,
                text=chapter_text,
                content_hash=_hash(chapter_text),
                scenes=scenes,
            )
        )

    if not any(scene.chunks for chapter in chapters for scene in chapter.scenes):
        raise ValueError("Manuscript contains no chunkable text")
    metadata = {
        "parser_version": PARSER_VERSION,
        "tokenizer_version": TOKENIZER_VERSION,
        "chapter_detection": detection,
        "warnings": warnings,
        "chunking": asdict(config),
    }
    if suffix in {".md", ".txt"}:
        metadata["detected_boundaries"] = {
            "coordinate_system": "normalized_text_line_1_based",
            "chapters": [
                block.source_line
                for block in blocks
                if block.heading and block.source_line is not None
            ],
            "scenes": scene_boundary_lines,
        }
    return ParsedManuscript(
        chapters=chapters,
        metadata=metadata,
    )
