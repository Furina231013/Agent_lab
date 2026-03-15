"""Split text with paragraph-first boundaries and char fallback for long blocks.

This keeps chunk boundaries more readable in simple documents while preserving
the old overlap behavior for recall near chunk edges.
"""

from __future__ import annotations

import re

from app.config import settings
from app.schemas import ChunkItem
from app.utils.text import split_paragraphs

ASCII_SENTENCE_ENDINGS = {".", "!", "?", ";"}
CJK_SENTENCE_ENDINGS = {"。", "！", "？", "；"}
SENTENCE_CLOSERS = {'"', "'", "”", "’", "）", "】", "》", "」", "』"}
START_SNAP_LOOKAHEAD = 80


def _build_chunk_id(source: str, index: int, start: int) -> str:
    safe_source = re.sub(r"[^a-zA-Z0-9]+", "_", source).strip("_") or "document"
    return f"{safe_source}-{index:04d}-{start:06d}"


def _build_paragraph_boundaries(paragraphs: list[str]) -> list[int]:
    boundaries: list[int] = []
    cursor = 0
    for index, paragraph in enumerate(paragraphs):
        cursor += len(paragraph)
        boundaries.append(cursor)
        if index < len(paragraphs) - 1:
            cursor += 2
    return boundaries


def _build_sentence_boundaries(document_text: str) -> list[int]:
    boundaries: list[int] = []
    text_length = len(document_text)
    for index, character in enumerate(document_text):
        is_sentence_end = character in CJK_SENTENCE_ENDINGS
        if character in ASCII_SENTENCE_ENDINGS:
            next_character = document_text[index + 1] if index + 1 < text_length else ""
            is_sentence_end = next_character == "" or next_character.isspace()
        if not is_sentence_end:
            continue

        boundary = index + 1
        while boundary < text_length and document_text[boundary] in SENTENCE_CLOSERS:
            boundary += 1
        boundaries.append(boundary)
    return boundaries


def _build_sentence_starts(
    document_text: str,
    sentence_boundaries: list[int],
) -> list[int]:
    starts: list[int] = []
    text_length = len(document_text)
    for boundary in sentence_boundaries:
        start = boundary
        while start < text_length and document_text[start].isspace():
            start += 1
        if start < text_length:
            starts.append(start)
    return starts


def _preferred_end(boundaries: list[int], start: int, max_end: int) -> int:
    chosen_boundary = 0
    for boundary in boundaries:
        if boundary > max_end:
            break
        if start < boundary <= max_end:
            chosen_boundary = boundary
    return chosen_boundary or max_end


def _preferred_start(sentence_starts: list[int], raw_start: int, text_length: int) -> int:
    max_candidate = min(
        text_length,
        raw_start + settings.chunk_overlap + START_SNAP_LOOKAHEAD,
    )
    for sentence_start in sentence_starts:
        if raw_start < sentence_start <= max_candidate:
            return sentence_start
    return raw_start


def _trim_chunk_bounds(document_text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and document_text[start].isspace():
        start += 1
    while end > start and document_text[end - 1].isspace():
        end -= 1
    return start, end


def chunk_text(source: str, text: str) -> list[ChunkItem]:
    paragraphs = split_paragraphs(text)
    if not paragraphs:
        raise ValueError("Cannot chunk an empty document.")

    if settings.chunk_size - settings.chunk_overlap <= 0:
        raise ValueError("Chunk overlap must be smaller than chunk size.")

    document_text = "\n\n".join(paragraphs)
    paragraph_boundaries = _build_paragraph_boundaries(paragraphs)
    sentence_boundaries = _build_sentence_boundaries(document_text)
    boundaries = sorted(set(paragraph_boundaries + sentence_boundaries))
    sentence_starts = _build_sentence_starts(document_text, sentence_boundaries)
    chunks: list[ChunkItem] = []
    start = 0
    index = 0
    text_length = len(document_text)

    while start < text_length:
        max_end = min(start + settings.chunk_size, text_length)
        end = _preferred_end(boundaries, start, max_end)
        start, end = _trim_chunk_bounds(document_text, start, end)
        chunk_value = document_text[start:end]
        if chunk_value:
            chunks.append(
                ChunkItem(
                    chunk_id=_build_chunk_id(source, index, start),
                    source=source,
                    text=chunk_value,
                    start_index=start,
                    end_index=end,
                )
            )
        if end >= text_length:
            break

        chunk_length = end - start
        if chunk_length <= settings.chunk_overlap:
            next_start = end
        else:
            next_start = end - settings.chunk_overlap
        start = _preferred_start(sentence_starts, next_start, text_length)
        index += 1

    return chunks
