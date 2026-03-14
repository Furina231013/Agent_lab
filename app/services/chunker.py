"""Split text with paragraph-first boundaries and char fallback for long blocks.

This keeps chunk boundaries more readable in simple documents while preserving
the old overlap behavior for recall near chunk edges.
"""

from __future__ import annotations

import re

from app.config import settings
from app.schemas import ChunkItem
from app.utils.text import split_paragraphs


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


def _preferred_end(boundaries: list[int], start: int, max_end: int) -> int:
    chosen_boundary = 0
    for boundary in boundaries:
        if boundary > max_end:
            break
        if start < boundary <= max_end:
            chosen_boundary = boundary
    return chosen_boundary or max_end


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
    boundaries = _build_paragraph_boundaries(paragraphs)
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
            start = end
        else:
            start = end - settings.chunk_overlap
        index += 1

    return chunks
